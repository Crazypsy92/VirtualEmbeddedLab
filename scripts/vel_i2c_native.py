"""Run one Zephyr native_sim controller and compare its result with device events."""
import errno
import os
import select
import subprocess
import time

from vel_i2c import EEPROM, REGISTER


class NativeController:
    def __init__(self, executable, log):
        self.log = log
        self.pending = b""
        self.process = subprocess.Popen([executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, bufsize=0)
        try:
            self.send(f"INIT {REGISTER} {EEPROM}")
            if self.receive("READY") != ["READY"]:
                raise RuntimeError("Unexpected native I2C startup message")
        except BaseException:
            self.close()
            raise

    def send(self, line):
        self.log.write("> " + line + "\n")
        self.log.flush()
        self.process.stdin.write((line + "\n").encode("ascii"))

    def receive(self, prefix):
        deadline = time.monotonic() + 4
        fd = self.process.stdout.fileno()
        while True:
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                decoded = line.decode(errors="replace").strip()
                self.log.write("< " + decoded + "\n")
                self.log.flush()
                fields = decoded.split()
                if fields and fields[0] in ("READY", "CALL", "DONE"):
                    if fields[0] != prefix:
                        raise RuntimeError(f"Expected {prefix}, got {decoded}")
                    return fields
            remain = deadline - time.monotonic()
            if remain <= 0 or not select.select([fd], [], [], remain)[0]:
                raise TimeoutError(f"Zephyr I2C {prefix} deadline reached")
            chunk = os.read(fd, 4096)
            if not chunk:
                raise ConnectionError(f"Zephyr I2C closed before {prefix}")
            self.pending += chunk
            if len(self.pending) > 65536:
                raise RuntimeError("Zephyr I2C response exceeds limit")

    def transfer(self, request, present, execute):
        payload = request.write_bytes.hex() or "-"
        length = request.read_length
        self.send(f"GO {request.khz} {request.address} {length} {payload}")
        call = None
        if present:
            _, addr, count, first, second, read_len, written = self.receive("CALL")
            call = list(map(int, [addr, count, first, second, read_len]))
            # Zephyr i2c_msg flags: READ=1, STOP=2, RESTART=4.
            combined = bool(request.write_bytes and length)
            flags = [0, 7] if combined else [3 if length else 2, 0]
            expected = [request.address, 2 if combined else 1, *flags, length]
            if call != expected or payload != written:
                raise RuntimeError(f"Unexpected native I2C message: {call} {written}")
        status, data = execute()
        code = {"OK": 0, "NACK": -errno.EIO, "ABORTED": -errno.ECANCELED,
                "MODEL_MISMATCH": -errno.EINVAL}[status]
        if present:
            self.send(f"{code} {data.hex() or '-'}")
        _, rc, speed, received = self.receive("DONE")
        if (int(rc), int(speed), received) != (code, 1 if request.khz == 100 else 2, data.hex() or "-"):
            raise RuntimeError(f"Zephyr I2C result differs: {rc} {speed} {received}")
        return {"rc": int(rc), "speed_flag": int(speed), "callback": call,
                "read_hex": "" if received == "-" else received}

    def close(self):
        p = self.process
        p.stdin.close()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=2)
        finally:
            p.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
