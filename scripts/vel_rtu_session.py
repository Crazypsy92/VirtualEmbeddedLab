"""Record real pyserial reads and writes around each pymodbus transaction."""
from pathlib import Path
import json
import sys
import time

from vel_rtu_frames import pair

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host/modbus_master"))
from pty_control import PtySerialClient, wait_rx_ready


class TransactionError(RuntimeError):
    pass


class SessionTransportError(TransactionError):
    """The PTY control or data stream must be reset before sending again."""


class RecordedMaster:
    def __init__(self, port, control, frames, transactions):
        self.control = control
        self.frames = frames
        self.transactions = transactions
        self.sequence = 0
        self.client = PtySerialClient(port, baudrate=115200, parity="N", timeout=.15, retries=0)
        if not self.client.connect():
            raise ConnectionError("无法连接 RTU PTY")
        self.port = self.client.socket
        self.read_bytes = self.port.read
        self.write_bytes = self.port.write
        self.port.read, self.port.write = self.read, self.write

    def read(self, size):
        data = self.read_bytes(size)
        if data:
            clock = time.monotonic_ns()
            if self.tx:
                self.rx.extend(data)
                self.rx_ns = clock
            else:
                self.stale.extend(data)
        return data

    def write(self, data):
        if self.tx_ns is None:
            self.tx_ns = time.monotonic_ns()
        count = self.write_bytes(data)
        self.tx.extend(data[:count])
        return count

    def call(self, method, *args, device_id=1, purpose="请求", **kwargs):
        self.sequence += 1
        self.tx, self.rx, self.stale = bytearray(), bytearray(), bytearray()
        self.tx_ns = self.rx_ns = None
        started = time.monotonic_ns()
        result = None
        error = None
        caught = None
        try:
            wait_rx_ready(self.control)
            result = getattr(self.client, method)(*args, device_id=device_id, **kwargs)
            if result.isError():
                error = str(result)
        except BaseException as exc:
            caught = exc
            error = str(exc)
        finally:
            finished = time.monotonic_ns()
            checked = pair(self.tx, self.rx)
            if self.stale:
                checked.update(status="STALE_RX", matched=False, error="请求发送前发现残留字节")
            elif not self.tx:
                checked.update(status="NOT_SENT", matched=False, error=error or "未写入串口")
            elif error and checked["status"] == "PASS":
                checked.update(status="CLIENT_ERROR", error=error)
            checked.update(sequence=self.sequence, monotonic_ns=started, tx_ns=self.tx_ns,
                           rx_ns=self.rx_ns, finished_ns=finished, purpose=purpose,
                           latency_ms=(self.rx_ns - self.tx_ns) / 1e6
                           if self.tx_ns is not None and self.rx_ns is not None else None,
                           transport_error=error, pre_tx_rx_hex=self.stale.hex())
            for frame in (checked["tx"], checked["rx"]):
                if frame["byte_length"]:
                    self.frames.write(json.dumps({"sequence": self.sequence,
                                                 "monotonic_ns": self.tx_ns if frame["direction"] == "TX" else self.rx_ns,
                                                 "direction": frame["direction"].lower(),
                                                 "hex": frame["raw_hex"]}) + "\n")
            self.frames.flush()
            self.transactions.write(json.dumps(checked, ensure_ascii=False) + "\n")
            self.transactions.flush()
        if caught is not None and not isinstance(caught, Exception):
            raise caught
        if checked["status"] in ("NOT_SENT", "STALE_RX"):
            raise SessionTransportError(f"#{self.sequence} {checked['status']} · {checked['error']}")
        if checked["status"] != "PASS":
            raise TransactionError(f"#{self.sequence} {checked['status']} · {checked['error'] or error}")
        return result

    def close(self):
        self.client.close()


READ = {1: ("read_coils", 8), 2: ("read_discrete_inputs", 4),
        3: ("read_holding_registers", 8), 4: ("read_input_registers", 8)}
REGISTER_LIMITS = [(0, 2), (1, 1000), (0, 1000), (0, 255), (1, 1000)]


def validate_protocol(command):
    fc = command.get("fc")
    unit, address, values = (command.get(key) for key in ("unit", "address", "values"))
    if type(fc) is not int or type(unit) is not int or not 1 <= unit <= 247:
        raise ValueError("从站地址范围为 1–247")
    if type(address) is not int or address < 0:
        raise ValueError("起始地址必须为非负整数")
    if fc in READ:
        count = command.get("count")
        if set(command) == {"op", "fc", "unit", "address", "count"} and type(count) is int and 1 <= count <= READ[fc][1] - address:
            return
        raise ValueError("读取地址或数量超出设备映射")
    if fc not in (5, 6, 15, 16) or set(command) != {"op", "fc", "unit", "address", "values"}:
        raise ValueError("不支持的协议操作")
    if not isinstance(values, list) or not values:
        raise ValueError("至少输入一个值")
    if fc in (5, 6) and len(values) != 1:
        raise ValueError("单写操作需要一个值")
    # The current native_sim target is unit 1. Other unit addresses remain
    # available for read-only timeout demonstrations.
    if unit != 1:
        raise ValueError("写入只允许从站 1")
    if fc in (5, 15):
        if address + len(values) <= 8 and all(type(v) is int and v in (0, 1) for v in values):
            return
        raise ValueError("线圈 0–7 可写，输入值为 0 或 1")
    limits = REGISTER_LIMITS[address:address + len(values)]
    if len(limits) != len(values) or any(type(v) is not int or not lo <= v <= hi
                                         for v, (lo, hi) in zip(values, limits)):
        raise ValueError("保持寄存器 0–4 可写，值必须符合寄存器表")


def run_protocol(command, call):
    fc, address, unit = (command[key] for key in ("fc", "address", "unit"))
    if fc in READ:
        count = command["count"]
        response = call(READ[fc][0], address, count=count, device_id=unit)
        values = [int(b) for b in response.bits[:count]] if fc <= 2 else response.registers
        return {"values": values, "verified": None}
    values = command["values"]
    if fc in (5, 15):
        bits = [bool(v) for v in values]
        call("write_coil" if fc == 5 else "write_coils", address, bits[0] if fc == 5 else bits)
        coils = call("read_coils", 0, count=8, purpose="写入回读").bits[:8]
        bitmap = call("read_input_registers", 7, count=1, purpose="GPIO 位图回读").registers[0]
        if coils[address:address + len(bits)] != bits or bitmap != sum(int(b) << i for i, b in enumerate(coils)):
            raise TransactionError("FC01 和 IR7 未能确认线圈写入")
        return {"values": [int(b) for b in coils], "do_bitmap": bitmap, "verified": True}
    call("write_register" if fc == 6 else "write_registers", address, values[0] if fc == 6 else values)
    actual = call("read_holding_registers", address, count=len(values), purpose="写入回读").registers
    if actual != values:
        raise TransactionError("FC03 未能确认保持寄存器写入")
    if address <= 3 < address + len(values):
        bitmap = call("read_input_registers", 7, count=1, purpose="GPIO 位图回读").registers[0]
        if bitmap != values[3 - address]:
            raise TransactionError("IR7 未能确认保持寄存器 3 的 GPIO 位图")
    return {"values": actual, "verified": True}
