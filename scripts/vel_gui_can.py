"""Run a real Zephyr CAN software loopback session for the GUI or integration test."""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time
import tty

from vel_can_frames import FILTERS, IDE, parse_request
from vel_env import ROOT, native_build
from vel_jobs import install_cancel_handlers

APP = ROOT / "zephyr/apps/backend_smoke/native_sim"


def event(kind, **fields):
    print(json.dumps({"event": kind, **fields}, ensure_ascii=False), flush=True)


class CanSession:
    def __init__(self, process, log, transactions):
        self.process = process
        self.stream = process.stdout.fileno()
        self.log = log
        self.transactions = transactions
        self.unread = bytearray()
        self.control = None
        self.sequence = 0

    def line(self, deadline):
        while b"\n" not in self.unread:
            remain = deadline - time.monotonic()
            if remain <= 0 or not select.select([self.stream], [], [], remain)[0]:
                raise TimeoutError("未收到 Zephyr CAN 事件")
            data = os.read(self.stream, 65536)
            if not data:
                raise ConnectionError(f"Zephyr 进程输出结束，退出码 {self.process.poll()}")
            self.log.write(data)
            self.log.flush()
            self.unread.extend(data)
        line, self.unread = self.unread.split(b"\n", 1)
        return line.decode(errors="replace")

    def connect(self):
        deadline = time.monotonic() + 10
        path = None
        while True:
            line = self.line(deadline)
            if match := re.search(r"uart_1 connected to pseudotty: (/dev/pts/\d+)", line):
                path = match[1]
            if line == "CAN_READY":
                if not path:
                    raise ConnectionError("未发现 CAN 控制 PTY")
                self.control = os.open(path, os.O_RDWR | os.O_NOCTTY)
                tty.setraw(self.control)
                return path

    def transmit(self, frame, mode):
        sequence = self.sequence + 1
        return self.exchange(frame.packet(sequence, mode), frame.fields(), mode)

    def exchange(self, packet, expected, mode):
        self.sequence += 1
        sequence = self.sequence
        started = time.monotonic_ns()
        record = {"sequence": sequence, "monotonic_ns": started, "filter": mode,
                  "requested": expected, "tx": None, "rx": [], "latency_ms": None,
                  "status": "ERROR", "matched": False, "error": None}
        try:
            if os.write(self.control, packet) != len(packet):
                raise OSError("CAN 控制请求写入不完整")
            rc, actual_filter = self.receive(sequence, record)
            record.update(api_result=rc, active_filter=actual_filter)
            self.classify(record)
        except TimeoutError as error:
            record.update(status="TIMEOUT", error=str(error), stream_failed=True)
        except (OSError, ValueError, IndexError) as error:
            record.update(error=str(error), stream_failed=True)
        record["finished_ns"] = time.monotonic_ns()
        self.transactions.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.transactions.flush()
        return record

    def receive(self, sequence, record):
        deadline = time.monotonic() + .75
        while True:
            line = self.line(deadline).split()
            if not line or line[0] not in ("CAN_FRAME", "CAN_DONE"):
                continue
            if int(line[1]) != sequence:
                raise ValueError(f"收到其他事务的 CAN 记录 #{line[1]}")
            if line[0] == "CAN_DONE":
                return int(line[2]), int(line[3])
            _, _, direction, millis, identifier, flags, dlc, payload, queue = line
            flag_bits = int(flags, 16)
            fields = {"id": int(identifier, 16), "ide": bool(flag_bits & IDE), "flags": flag_bits,
                      "dlc": int(dlc), "data": "" if payload == "-" else payload,
                      "sim_ms": int(millis), "host_ns": time.monotonic_ns(), "queue": int(queue)}
            if fields["dlc"] * 2 != len(fields["data"]):
                raise ValueError("固件记录的 DLC 和 DATA 长度不一致")
            if direction == "TX" and record["tx"] is None and not record["rx"]:
                record["tx"] = fields
            elif direction == "RX" and record["tx"] is not None:
                record["rx"].append(fields)
            else:
                raise ValueError("CAN 实际 TX/RX 记录顺序不正确或 TX 重复")

    @staticmethod
    def classify(record):
        tx, received, expected = (record[key] for key in ("tx", "rx", "requested"))
        rc, active = record["api_result"], record["active_filter"]
        if rc != 0:
            status = "INVALID" if tx is None and rc == -errno.EINVAL else "ERROR"
            record.update(status=status, error=f"Zephyr 返回 {rc}")
            return
        if tx is None or active != FILTERS[record["filter"]] or any(tx[key] != expected[key] for key in expected):
            record.update(status="MISMATCH", error="固件提交帧或生效过滤器与请求不一致")
            return
        expected_queue = 2 if tx["ide"] else 1
        if not received:
            if active not in (0, expected_queue):
                record.update(status="FILTERED")
            else:
                record.update(status="TIMEOUT", error="CAN API 接收队列无回环帧")
            return
        if active not in (0, expected_queue) or len(received) != 1:
            record.update(status="MISMATCH", error="过滤结果异常或收到重复帧")
            return
        rx = received[0]
        record["latency_ms"] = (rx["host_ns"] - record["monotonic_ns"]) / 1e6
        if rx["queue"] != expected_queue or any(rx[key] != tx[key] for key in expected):
            record.update(status="MISMATCH", error="接收队列、ID、IDE、DLC、flags 或 DATA 不匹配")
            return
        record.update(status="PASS", matched=True)

    def close(self):
        if self.control is not None:
            os.close(self.control)


@contextmanager
def native_session(folder):
    build = folder / "can-build"
    with (folder / "build.log").open("w") as log:
        native_build(APP, build, options=("-DVEL_CAN_INSPECTOR=ON",), log=log)
    with ((folder / "can-firmware.log").open("wb") as log,
          (folder / "can-transactions.jsonl").open("w") as transactions):
        process = subprocess.Popen([build / "zephyr/zephyr.exe", "-rt", "-stop_at=175"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        session = CanSession(process, log, transactions)
        try:
            path = session.connect()
            yield session, path
        finally:
            session.close()
            if process.poll() is None:
                process.terminate()
            try:
                tail, _ = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                tail, _ = process.communicate(timeout=3)
            log.write(tail)
            (folder / "can-exit.json").write_text(json.dumps({"pid": process.pid, "exit": process.returncode}))


def run(folder):
    with native_session(folder) as (session, path):
        event("can_ready", control_pty=path)
        while raw := sys.stdin.buffer.readline(4097):
            counts = {}
            try:
                request = json.loads(raw)
                frame, mode, count = parse_request(request)
            except (ValueError, TypeError) as error:
                event("can_error", reason=str(error))
                if not raw.endswith(b"\n"):
                    return 1
                continue
            for _ in range(count):
                record = session.transmit(frame, mode)
                status = record["status"]
                counts[status] = counts.get(status, 0) + 1
                if record.get("stream_failed"):
                    event("can_error", reason=record["error"])
                    return 1
            event("can_result", counts=counts)
    return 0


if __name__ == "__main__":
    install_cancel_handlers()
    try:
        sys.exit(run(Path(sys.argv[1])))
    except Exception as error:
        event("can_error", reason=str(error))
        sys.exit(1)
