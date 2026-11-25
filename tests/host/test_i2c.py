"""Exercise identical I2C transactions over Host and Zephyr's I2C emulator."""
from collections import Counter
from contextlib import ExitStack
import json
import os
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_i2c import Bus, EEPROM, FIRST, LAST, REGISTER, Request, decode
from vel_i2c_native import NativeController
from vel_i2c_session import command


def evidence():
    path = os.environ.get("VEL_I2C_EVIDENCE")
    return Path(path) if path else None


class Suite:
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.adapter = None
        if self.native:
            executable = Path(os.environ["VEL_I2C_EXECUTABLE"])
            log = self.stack.enter_context((evidence() / f"native-{self._testMethodName}.log").open("w"))
            self.adapter = self.stack.enter_context(NativeController(executable, log))
            pid = self.adapter.process.pid
            self.addCleanup(self.cleaned, pid)
        self.bus = Bus(self.adapter)

    def cleaned(self, pid):
        self.stack.close()
        self.assertFalse(Path(f"/proc/{pid}").exists())

    def tx(self, operation, address, **kwargs):
        return self.bus.transfer(Request(operation, address, **kwargs))

    def read(self, addr=REGISTER, offset=0, length=1, khz=100):
        op = "register-read" if addr == REGISTER else "random-read"
        return self.tx(op, addr, offset=offset, length=length, khz=khz)

    def note(self, name, **values):
        if folder := evidence():
            backend = self.bus.metadata["backend"]
            with (folder / f"{backend}-results.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"case": name, "backend": backend, **values}, ensure_ascii=False) + "\n")

    def test_scan_and_address_stage(self):
        rows = self.bus.scan(100)
        self.assertEqual([r["request"]["address"] for r in rows], list(range(FIRST, LAST + 1)))
        good = [r["request"]["address"] for r in rows if r["status"] == "OK"]
        self.assertEqual(good, [REGISTER, EEPROM])
        for row in rows:
            start, addr, stop = list(decode(row["events"]))
            self.assertEqual(start["kind"], "START")
            self.assertEqual((addr["address"], addr["direction"]), (row["request"]["address"], "W"))
            self.assertEqual(stop["kind"], "STOP")
            self.assertEqual(addr["ack"], row["request"]["address"] in good)
            if not addr["ack"]:
                self.assertEqual(row["fault_at"], "address")
            if self.native:
                self.assertEqual(row["native"]["callback"] is not None, addr["ack"])
        self.note("scan", addresses=len(rows), found=good, status=dict(Counter(r["status"] for r in rows)),
                  missing=rows[0])

    def test_register_read_write(self):
        for offset, written in [(255, "cd"), (5, "12 34 ab")]:
            w = self.tx("register-write", REGISTER, offset=offset, data=written)
            self.assertEqual(w["status"], "OK")
            r = self.read(offset=offset, length=len(bytes.fromhex(written)), khz=400)
            self.assertEqual(bytes.fromhex(r["data"]), bytes.fromhex(written))
        self.note("register", write=w, read=r)

    def test_eeprom_write_poll_cross_page_and_sequential_rollover(self):
        self.assertEqual(self.read(EEPROM, 6, 4)["data"], "ffffffff")
        w = self.tx("page-write", EEPROM, offset=6, data="11 22 33 44")
        self.assertEqual(w["status"], "OK")
        busy = self.tx("probe", EEPROM)
        self.assertEqual((busy["status"], busy["fault_at"]), ("NACK", "address"))
        self.assertIn("写周期", busy["reason"])
        self.bus.idle(5000)
        row = self.read(EEPROM, 0, 10, 400)
        self.assertEqual(row["data"], "3344ffffffff1122ffff")
        self.read(EEPROM, 255)
        seq = self.tx("sequential-read", EEPROM, length=2)
        self.assertEqual(seq["data"], "3344")
        self.assertEqual([e["kind"] for e in seq["events"]], ["START", "ADDRESS", "DATA", "DATA", "STOP"])
        self.note("eeprom", page_write=w, busy=busy, random_read=row, sequential=seq)

    def test_repeated_start_and_timing(self):
        for ordinal in range(120):
            address = [REGISTER, EEPROM][ordinal % 2]
            length, offset = 1 + ordinal % 6, ordinal
            rate = [100, 400][ordinal // 2 % 2]
            row = self.read(address, offset, length, rate)
            events = list(decode(row["events"]))
            self.assertEqual([e["kind"] for e in events], ["START", "ADDRESS", "POINTER", "RESTART",
                                                         "ADDRESS"] + ["DATA"] * length + ["STOP"])
            self.assertEqual([(e["value"], e["direction"], e["ack"])
                              for e in (events[1], events[4])], [(address * 2, "W", True),
                                                               (address * 2 + 1, "R", True)])
            self.assertEqual(events[2]["value"], offset)
            self.assertEqual([e["ack"] for e in events[5:-1]], [True] * (length - 1) + [False])
            self.assertTrue(all(e["ack_by"] == "controller" for e in events[5:-1]))
            period = 10_000 if rate == 100 else 2_500
            self.assertEqual(row["period_ns"], period)
            edges = row["edges"]
            for event in events:
                if "bits" not in event:
                    idx = next(i for i, s in enumerate(edges) if s["ns"] == event["edge_ns"])
                    a, b = edges[idx - 1:idx + 1]
                    self.assertEqual((a["scl"], b["scl"]), (1, 1))
                    self.assertEqual((a["sda"], b["sda"]), (0, 1) if event["kind"] == "STOP" else (1, 0))
                    continue
                span = [x for x in edges if event["start_ns"] <= x["ns"] < event["end_ns"]]
                self.assertEqual([e["scl"] for e in span], [0, 1] * 9)
                self.assertEqual([e["sda"] for e in span[::2]], event["bits"])
                self.assertEqual([e["sda"] for e in span[1::2]], event["bits"])
                self.assertTrue(all(b["ns"] - a["ns"] == period // 2 for a, b in zip(span, span[1:])))
                expected = f"{event['value']:08b}{int(not event['ack'])}"
                self.assertEqual("".join(map(str, event["bits"])), expected)
            if self.native:
                self.assertEqual(row["native"]["callback"], [address, 2, 0, 7, length])
                self.assertEqual(row["native"]["speed_flag"], 1 if rate == 100 else 2)
            if ordinal in (1, 3):
                self.note("timing_example", trace=row)
        self.note("repeated_start", checked=ordinal + 1)

    def test_mixed_thousand(self):
        rng = random.Random(85)
        reqs = []
        memory = {}
        # 500 write/read pairs with independently built expectations.
        for ordinal in range(500):
            length = rng.randrange(1, 5)
            payload = rng.randbytes(length)
            offset = rng.randrange(0, 252)
            addr = REGISTER if ordinal % 2 else EEPROM
            if addr == EEPROM:
                offset &= ~7  # normal bulk writes aligned; page-wrap covered independently
                reqs.append(Request("page-write", addr, offset=offset, data=payload.hex()))
                reqs.append(Request("random-read", addr, offset=offset, length=length, khz=400))
            else:
                reqs.append(Request("register-write", addr, offset=offset, data=payload.hex()))
                reqs.append(Request("register-read", addr, offset=offset, length=length, khz=400))
            memory[2 * ordinal + 2] = payload
        observed = []
        for req in reqs:
            row = self.bus.transfer(req)
            self.assertEqual(row["status"], "OK")
            observed.append(row["sequence"])
            if req.operation.endswith("read"):
                self.assertEqual(bytes.fromhex(row["data"]), memory[row["sequence"]])
            elif req.operation == "page-write":
                self.bus.idle(5000)
        self.assertEqual(observed, list(range(1, len(reqs) + 1)))
        self.assertEqual(len(observed), 1000)
        self.note("mixed", count=len(observed), first=observed[0], last=observed[-1], readbacks=len(memory))

    def test_faults_recovery_and_invalid_no_wire(self):
        bad = self.tx("register-read", 0x29)
        mismatch = self.tx("random-read", REGISTER)
        nack = self.tx("register-write", REGISTER, fault="nack", fault_byte=1, data="99")
        abort = self.tx("register-write", REGISTER, fault="abort", fault_byte=1, data="99")
        busy = self.tx("probe", EEPROM, fault="busy")
        timeout = self.tx("probe", EEPROM, fault="timeout")
        self.assertEqual([x["status"] for x in [bad, mismatch, nack, abort, busy, timeout]],
                         ["NACK", "MODEL_MISMATCH", "NACK", "ABORTED", "BUSY", "TIMEOUT"])
        for event in (bad, mismatch, nack, abort):
            self.assertEqual(event["events"][-1]["kind"], "STOP")
        self.assertEqual([x["fault_at"] for x in [bad, mismatch, nack, abort]],
                         ["address", "address", 2, 2])
        self.assertFalse(list(decode(nack["events"]))[-2]["ack"])
        self.assertTrue(list(decode(abort["events"]))[-2]["ack"])
        for event in (busy, timeout):
            self.assertEqual(event["events"], [])
            self.assertEqual(event["fault_at"], "bus")
            self.assertEqual([(e["scl"], e["sda"]) for e in event["edges"]], [(1, 0)])
        self.assertEqual(timeout["end_ns"] - timeout["start_ns"], 25_000_000)
        before = self.bus.sequence
        for invalid in ({"address": 0}, {"address": 128}, {"length": 0}, {"length": 33},
                        {"operation": "register-write", "data": ""},
                        {"offset": 255, "length": 2}, {"operation": "page-write", "data": "ff" * 9},
                        {"operation": "register-write", "data": "ab", "fault": "nack", "fault_byte": 3}):
            params = {"operation": "register-read", "address": REGISTER} | invalid
            with self.assertRaises(ValueError):
                command(self.bus, {"op": "transfer", "request": params})
        self.assertEqual(self.bus.sequence, before)
        for i in range(100):
            self.assertEqual(self.read()["data"], "00")
        self.note("recovery", transactions=self.bus.sequence - before, invalid=8,
                  failures=[bad, mismatch, nack, abort, busy, timeout])


class Host(Suite, unittest.TestCase):
    native = False


@unittest.skipUnless(os.environ.get("VEL_I2C_EXECUTABLE"), "Native I2C executable not configured")
class Zephyr(Suite, unittest.TestCase):
    native = True


if __name__ == "__main__":
    unittest.main(verbosity=2)
