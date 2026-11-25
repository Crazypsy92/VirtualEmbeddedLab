"""I2C device state and wire events on a deterministic, simulated clock."""
from dataclasses import dataclass

SCOPE = "SIMULATED"
REGISTER = 0x28
EEPROM = 0x50
FIRST, LAST = 0x08, 0x77
MAX_DATA = 32
PAGE_SIZE = 8
WRITE_NS = 5_000_000
FAULTS = ("none", "nack", "abort", "busy", "timeout")
READS = ("register-read", "random-read", "sequential-read")
WRITES = ("register-write", "page-write")
OPERATIONS = ("probe", *READS, *WRITES)


@dataclass(frozen=True)
class Request:
    operation: str
    address: int
    khz: int = 100
    offset: int = 0
    length: int = 1
    data: str = ""
    fault: str = "none"
    fault_byte: int = 0

    def __post_init__(self):
        integer(self.address, FIRST, LAST, "7-bit 地址")
        if type(self.khz) is not int or self.khz not in (100, 400):
            raise ValueError("速率必须为 100 或 400 kHz")
        if self.operation not in OPERATIONS or self.fault not in FAULTS:
            raise ValueError("操作或故障类型无效")
        integer(self.offset, 0, 255, "寄存器偏移")
        integer(self.length, 1, MAX_DATA, "读取长度")
        if not isinstance(self.data, str) or len(self.data) > 3 * MAX_DATA:
            raise ValueError("DATA 需要 1–32 个十六进制字节")
        expected = PAGE_SIZE if self.operation == "page-write" else MAX_DATA
        if self.operation in WRITES and not 1 <= len(self.payload) <= expected:
            raise ValueError(f"DATA 需要 1–{expected} 个十六进制字节")
        if self.operation not in WRITES and self.payload:
            raise ValueError("此操作无 DATA 输入")
        if self.operation.startswith("register-"):
            size = len(self.payload) if self.operation in WRITES else self.length
            if self.offset + size > 256:
                raise ValueError("寄存器地址范围越界")
        integer(self.fault_byte, 0, MAX_DATA, "故障字节下标")
        if self.fault in ("nack", "abort") and self.fault_byte >= len(self.write_bytes):
            raise ValueError("故障下标超出主机写入字节（从指针字节 0 开始）")

    @property
    def payload(self):
        return bytes.fromhex(self.data)

    @property
    def write_bytes(self):
        if self.operation in ("probe", "sequential-read"):
            return b""
        return bytes([self.offset]) + self.payload

    @property
    def read_length(self):
        return self.length if self.operation in READS else 0


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} 应在 {low}–{high}")
    return value


class Wire:
    def __init__(self, khz, start_ns):
        self.t = start_ns
        self.half = 500_000 // khz
        self.edges = [{"ns": self.t, "scl": 1, "sda": 1}]
        self.events = []

    def level(self, scl, sda):
        self.edges.append({"ns": self.t, "scl": scl, "sda": sda})
        self.t += self.half

    def boundary(self, kind):
        start = self.t
        if kind == "STOP":
            self.level(0, 0)
            self.level(1, 0)
            self.level(1, 1)
        else:
            if kind == "RESTART":
                self.level(0, 1)
            self.level(1, 1)
            self.level(1, 0)
        self.events.append({"kind": kind, "start_ns": start, "end_ns": self.t,
                            "edge_ns": self.edges[-1]["ns"]})

    def byte(self, kind, value, sender, ack, offset):
        start = self.t
        bits = [value >> shift & 1 for shift in range(7, -1, -1)] + [int(not ack)]
        for bit in bits:
            self.level(0, bit)
            self.level(1, bit)
        self.events.append({"kind": kind, "bits": bits, "sender": sender, "offset": offset,
                            "start_ns": start, "end_ns": self.t})


def decode(events):
    """Render fields directly from captured bit values."""
    for event in events:
        if "bits" not in event:
            yield event
            continue
        bits = event["bits"]
        value = int("".join(map(str, bits[:8])), 2)
        row = event | {"value": value, "ack": bits[8] == 0,
                       "ack_by": "target" if event["sender"] == "controller" else "controller"}
        if event["kind"] == "ADDRESS":
            row |= {"address": value >> 1, "direction": "R" if value & 1 else "W"}
        yield row


class Memory:
    def __init__(self, kind):
        self.kind = kind
        self.data = bytearray([255 if kind == "eeprom" else 0] * 256)
        self.pointer = 0
        self.ready_ns = 0

    def apply(self, request, wire):
        if request.write_bytes:
            self.pointer = request.offset
        if request.operation in WRITES:
            for pos, value in enumerate(request.payload):
                index = request.offset + pos
                if self.kind == "eeprom":
                    index = request.offset // PAGE_SIZE * PAGE_SIZE + index % PAGE_SIZE
                self.data[index] = value
                self.pointer = (index + 1) % 256
            if self.kind == "eeprom":
                self.ready_ns = wire.t + WRITE_NS
        if request.read_length:
            self.pointer = (self.pointer + request.read_length) % 256


class Bus:
    """Run the same device model directly on Host or through an I2C controller adapter."""
    def __init__(self, adapter=None):
        self.devices = {REGISTER: Memory("register"), EEPROM: Memory("eeprom")}
        self.adapter = adapter
        self.time_ns = 0
        self.sequence = 0

    @property
    def metadata(self):
        return {"scope": SCOPE, "backend": "zephyr-i2c-emul" if self.adapter else "host-i2c-model",
                "rates_khz": [100, 400],
                "devices": [{"address": addr, "model": dev.kind, "capacity": len(dev.data),
                             **({"page_size": PAGE_SIZE, "write_ns": WRITE_NS} if dev.kind == "eeprom" else {})}
                            for addr, dev in self.devices.items()]}

    def idle(self, microseconds):
        self.time_ns += integer(microseconds, 0, 25_000, "仿真等待 μs") * 1000

    def scan(self, khz):
        return [self.transfer(Request("probe", address, khz=khz)) for address in range(FIRST, LAST + 1)]

    def transfer(self, request):
        self.sequence += 1
        wire = Wire(request.khz, self.time_ns)
        dev = self.devices.get(request.address)
        result = {"status": "OK", "data": "", "fault_at": None, "reason": None,
                  "handling": "STOP"}
        native = None
        if request.fault in ("busy", "timeout"):
            wire.edges[0]["sda"] = 0
            wire.t += 25_000_000 if request.fault == "timeout" else wire.half
            result.update(status=request.fault.upper(), reason="总线未释放，未发送 START",
                          fault_at="bus", handling="超时退出" if request.fault == "timeout" else "退出等待")
        else:
            def execute():
                self.exchange(request, wire, dev, result)
                return result["status"], bytes.fromhex(result["data"])

            if self.adapter:
                native = self.adapter.transfer(request, dev is not None, execute)
            else:
                execute()
        self.time_ns = wire.t + wire.half
        return self.metadata | {"sequence": self.sequence, "request": request.__dict__,
                                "period_ns": 2 * wire.half, "start_ns": wire.edges[0]["ns"],
                                "end_ns": wire.t, "events": wire.events, "edges": wire.edges,
                                "native": native} | result

    @staticmethod
    def exchange(request, wire, dev, result):
        write = request.write_bytes
        count = request.read_length
        direction = int(not write and count > 0)
        wire.boundary("START")
        ack = dev is not None and wire.t >= dev.ready_ns
        wire.byte("ADDRESS", request.address << 1 | direction, "controller", ack, 0)
        if not ack:
            result.update(status="NACK", fault_at="address", reason="设备不存在" if dev is None else "EEPROM 写周期忙")
            wire.boundary("STOP")
            return
        device_op = "eeprom" if request.operation in ("random-read", "sequential-read", "page-write") else "register"
        wrong_model = request.operation != "probe" and dev.kind != device_op
        if wrong_model:
            result.update(status="MODEL_MISMATCH", fault_at="address", reason="地址应答，但设备类型与该操作不匹配")
            wire.boundary("STOP")
            return
        for i, byte in enumerate(write):
            inject = request.fault if i == request.fault_byte else "none"
            wire.byte("POINTER" if i == 0 else "DATA", byte, "controller", inject != "nack", i + 1)
            if inject in ("nack", "abort"):
                result.update(status="NACK" if inject == "nack" else "ABORTED", fault_at=i + 1,
                              reason="从设备拒收字节" if inject == "nack" else "主机中途终止")
                wire.boundary("STOP")
                return
        if write and count:
            wire.boundary("RESTART")
            wire.byte("ADDRESS", request.address << 1 | 1, "controller", True, len(write) + 1)
        if count:
            pointer = request.offset if write else dev.pointer
            data = bytes(dev.data[(pointer + i) % 256] for i in range(count))
            base = len(write) + (2 if write else 1)
            for i, byte in enumerate(data):
                wire.byte("DATA", byte, "target", i + 1 != count, base + i)
            result["data"] = data.hex()
        wire.boundary("STOP")
        dev.apply(request, wire)
