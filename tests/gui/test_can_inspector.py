"""Classical CAN input tests, Zephyr Loopback integration, and real WSLg UI checks."""
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from tempfile import mkdtemp
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_can_frames import CanFrame, parse_fields, parse_request
from vel_env import work


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify_shutdown(test, folder, worker=None, supervisor=None):
    data = json.loads((folder / "can-exit.json").read_text())
    test.assertEqual(data["exit"], 0)
    for pid in (data["pid"], worker, supervisor):
        if pid is not None:
            test.assertFalse(Path(f"/proc/{pid}").exists(), pid)
    for path in re.findall(r"/dev/pts/\d+", (folder / "can-firmware.log").read_text())[:2]:
        test.assertFalse(Path(path).exists(), path)


class Frames(unittest.TestCase):
    def test_standard_extended_boundaries(self):
        for format_, max_id, ide in (("Standard", "7ff", 0), ("Extended", "1fffffff", 1)):
            for value in ("0x0", max_id):
                tx = parse_fields(format_, value, "0", "")
                self.assertEqual(tx.fields()["flags"], ide)
                packed = struct.unpack(">cIIBBB8s", tx.packet(7, "extended"))
                self.assertEqual(packed[:6], (b"C", 7, int(value, 16), ide, 0, 2))

    def test_dlc_and_data(self):
        for number, hexdata in ((0, ""), (1, "00"), (8, "00 11 22 33 FC DD EE FF")):
            with self.subTest(dlc=number):
                tx = parse_fields("Standard", "0x120", str(number), hexdata)
                self.assertEqual(tx.dlc, number)
                self.assertEqual(tx.data.hex(), hexdata.lower().replace(" ", ""))

    def test_reject_malformed_fields(self):
        for item in (("Standard", "800", "0", ""), ("Extended", "20000000", "0", ""),
                     ("Standard", "ZZ", "1", "00"), ("Standard", "0", "9", "00"),
                     ("Standard", "0", "-1", ""), ("Standard", "0", "2", "00"),
                     ("Standard", "0", "1", "100"), ("Standard", "0", "1", "zz"),
                     ("Standard", "0", "1", "-1"), ("FD", "0", "0", "")):
            with self.subTest(item=item), self.assertRaises(ValueError):
                parse_fields(*item)

    def test_invalid_batch_or_filter(self):
        request = {"format": "Standard", "id": "123", "dlc": "1", "data": "01",
                   "filter": "all", "count": 1}
        self.assertEqual(parse_request(request)[1:], ("all", 1))
        for change in ({"count": 0}, {"count": 1001}, {"count": True}, {"filter": "bad"}):
            with self.assertRaises(ValueError):
                parse_request(request | change)


class Native(unittest.TestCase):
    def test_real_api_thousand_frames_and_filters(self):
        from vel_gui_can import native_session
        root = work("can-h1-test")
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(mkdtemp(prefix="loopback-", dir=root))
        with native_session(folder) as (can, _):
            for i in range(1000):
                is_extended = i % 2 == 1
                dlc = i % 9
                identifier = 0x1FFFF000 + i if is_extended else i // 2
                frame = CanFrame(identifier, is_extended, dlc, bytes((i + j * 37) % 256 for j in range(dlc)))
                row = can.transmit(frame, "all")
                self.assertEqual(row["status"], "PASS", row)
                self.assertEqual(len(row["rx"]), 1)
                self.assertEqual(row["rx"][0]["queue"], 2 if is_extended else 1)
            for mode, is_extended, expected in (("standard", False, "PASS"), ("standard", True, "FILTERED"),
                                                ("extended", False, "FILTERED"), ("extended", True, "PASS")):
                row = can.transmit(CanFrame(0x321, is_extended, 1, b"\xA5"), mode)
                self.assertEqual(row["status"], expected, row)
                self.assertEqual(len(row["rx"]), int(expected == "PASS"))
            for identifier, extended, dlc in ((0x800, 0, 0), (0x20000000, 1, 0), (2, 0, 9)):
                packet = struct.pack(">cIIBBB8s", b"C", can.sequence + 1, identifier, extended,
                                     dlc, 0, b"\x00" * 8)
                row = can.exchange(packet, None, "all")
                self.assertEqual(row["status"], "INVALID", row)
                self.assertIsNone(row["tx"])
                self.assertEqual(row["rx"], [])
        log = (folder / "can-firmware.log").read_text()
        evidence = records(folder / "can-transactions.jsonl")
        self.assertEqual([row["sequence"] for row in evidence], list(range(1, 1008)))
        for i, row in enumerate(evidence, 1):
            self.assertEqual(len(re.findall(rf"^CAN_DONE {i} ", log, re.M)), 1)
            for tag, count in (("TX", int(row["tx"] is not None)), ("RX", len(row["rx"]))):
                self.assertEqual(len(re.findall(rf"^CAN_FRAME {i} {tag} ", log, re.M)), count)
        self.assertEqual(len({(row["tx"]["id"], row["tx"]["ide"]) for row in evidence[:1000]}), 1000)
        verify_shutdown(self, folder)
        print(f"Native API evidence {folder}", flush=True)
        print("1000/1000 varying CAN frames, 0 lost/duplicates/mismatches. Filter: 2 match, 2 exclude. 3 rejected.", flush=True)


class Window(unittest.TestCase):
    def test_real_gui_single_batch_inspect_stop_and_close(self):
        self.assertTrue(os.environ.get("DISPLAY"), "A real WSLg display is required")
        import tkinter as tk
        from vel_gui_workbench import Workbench
        from vel_jobs import lock_status

        root = tk.Tk()
        app = Workbench(root)
        root.geometry("1200x850+35+35")
        stage = 0
        failures = []
        runs = []
        limit = time.monotonic() + 215

        def values(**settings):
            for field, value in settings.items():
                app.can_panel.form[field].set(value)

        def check():
            nonlocal stage
            try:
                self.assertLess(time.monotonic(), limit, (stage, app.status.get()))
                if stage == 0 and app.available is not None:
                    app.select("CAN")
                    self.assertEqual(app.mode.get(), "交互会话")
                    app.start_button.invoke()
                    runs.append((app.folder, app.job.pid))
                    stage = 1
                elif stage == 1 and app.live:
                    panel = app.can_panel
                    values(dlc="9")
                    panel.single.invoke()
                    self.assertIn("INVALID", panel.message.get())
                    self.assertFalse(app.pending)
                    values(dlc="4")
                    panel.single.invoke()
                    stage = 2
                elif stage == 2 and not app.pending and len(app.can_panel.rows) >= 1:
                    row = app.can_panel.rows["1"]
                    self.assertEqual((row["status"], row["tx"]["data"], row["rx"][0]["queue"]),
                                     ("PASS", "11223344", 1))
                    values(format="Extended", id="1FFFFFFF", filter="standard", dlc="0", data="")
                    app.can_panel.single.invoke()
                    stage = 3
                elif stage == 3 and not app.pending and len(app.can_panel.rows) >= 2:
                    self.assertEqual(app.can_panel.rows["2"]["status"], "FILTERED")
                    values(filter="extended", dlc="8", data="11 22 33 44 55 66 77 88", batch="12")
                    app.can_panel.batch.invoke()
                    stage = 4
                elif stage == 4 and not app.pending and len(app.can_panel.rows) >= 14:
                    panel = app.can_panel
                    self.assertEqual(panel.counters, {"tx": 14, "rx": 13, "matched": 13, "filtered": 1, "lost": 0})
                    panel.transactions.selection_set("14")
                    panel.select()
                    details = [panel.details.item(i, "values") for i in panel.details.get_children()]
                    self.assertIn(("帧格式 / IDE", "Extended / 1", "Extended / 1", "一致"), details)
                    self.assertIn(("DATA[7]", "88", "88", "一致"), details)
                    if target := os.environ.get("VEL_CAN_SCREENSHOTS"):
                        root.update()
                        root.after(110)
                        root.update()
                        subprocess.run(["import", "-window", hex(root.winfo_id()), str(Path(target) / "can.png")],
                                       check=True, timeout=12)
                    app.stop.invoke()
                    stage = 5
                elif stage == 5 and not app.job:
                    folder, pid = runs[0]
                    result = json.loads((folder / "result.json").read_text())
                    self.assertEqual(result["status"], "CANCELLED")
                    verify_shutdown(self, folder, result["pid"], pid)
                    self.assertFalse(lock_status(work("gui-h1/locks") / "can.lock")[0])
                    app.start_button.invoke()
                    runs.append((app.folder, app.job.pid))
                    stage = 6
                elif stage == 6 and app.live:
                    app.close()
                    stage = 7
                    return
            except Exception as error:
                failures.append(error)
                app.close()
                return
            root.after(90, check)

        root.after(90, check)
        root.mainloop()
        if failures:
            raise failures[0]
        self.assertEqual(stage, 7)
        folder, pid = runs[-1]
        result = json.loads((folder / "result.json").read_text())
        verify_shutdown(self, folder, result["pid"], pid)
        self.assertFalse(lock_status(work("gui-h1/locks") / "can.lock")[0])
        print(f"WSLg CAN evidence {runs[0][0]}", flush=True)
        print(f"WSLg window-close evidence {folder}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
