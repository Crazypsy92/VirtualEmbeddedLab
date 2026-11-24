"""Known Modbus RTU vectors plus real WSLg controls and PTY transactions."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_rtu_frames import crc16, decode, pair

VECTORS = [
    ("0101000000083dcc", "01010105918b", [1, 0, 1, 0, 0, 0, 0, 0]),
    ("01020000000479c9", "01020105618b", [1, 0, 1, 0]),
    ("010300000002c40b", "0103040001000a2bf4", [1, 10]),
    ("01040006000291ca", "010404000500012a45", [5, 1]),
    ("01050000ff008c3a", "01050000ff008c3a", [0xFF00]),
    ("010600010014d805", "010600010014d805", [20]),
    ("010f0000000801053e96", "010f00000008540d", None),
    ("011000000003060001000a01f4fb55", "0110000000038008", None),
]


class Frames(unittest.TestCase):
    def test_eight_functions(self):
        for tx, rx, values in VECTORS:
            with self.subTest(tx=tx):
                result = pair(bytes.fromhex(tx), bytes.fromhex(rx))
                self.assertTrue(result["matched"], result)
                self.assertEqual(result["status"], "PASS")
                for message in (result["tx"], result["rx"]):
                    self.assertTrue(message["crc_ok"])
                    decoded = message["decoded_fields"]
                    self.assertEqual([f["offset"] for f in decoded[:2]], [0, 1])
                    self.assertEqual(decoded[-2]["offset"], message["byte_length"] - 2)
                    self.assertEqual(decoded[-1]["offset"], message["byte_length"] - 1)
                    self.assertEqual("".join(f["raw_hex"] for f in decoded), message["raw_hex"])
                self.assertEqual(result["rx"].get("values"), values)
        tx = decode(bytes.fromhex(VECTORS[7][0]), True)
        self.assertEqual(tx["values"], [1, 10, 500])
        self.assertEqual([f["offset"] for f in tx["decoded_fields"][5:8]], [7, 9, 11])

    def test_bits_use_low_bit_first_and_follow_address(self):
        tx, rx = (bytes.fromhex(text) for text in ("010f00000009020101252c", "010f0000000995cd"))
        result = pair(tx, rx)
        self.assertEqual(result["status"], "PASS")
        data = result["tx"]["decoded_fields"]
        self.assertEqual(data[5]["value"][0], {"address": 0, "value": 1})
        self.assertEqual(data[6]["offset"], 8)
        self.assertEqual(data[6]["value"], [{"address": 8, "value": 1}])
        response = decode(bytes.fromhex("01010105918b"), False, {"address": 3, "quantity": 3})
        self.assertEqual(response["decoded_fields"][3]["value"],
                         [{"address": 3, "value": 1}, {"address": 4, "value": 0}, {"address": 5, "value": 1}])

    def test_known_crc_and_corruption(self):
        self.assertEqual(crc16(b"123456789"), 0x4B37)
        tx, rx, _ = VECTORS[0]
        result = pair(bytes.fromhex(tx), bytes.fromhex(rx[:-2] + "00"))
        self.assertFalse(result["matched"])
        self.assertEqual(result["status"], "CRC_ERROR")
        self.assertEqual(result["rx"]["crc_computed"], 0x8B91)

    def test_partial_timeout_and_length(self):
        tx, rx = (bytes.fromhex(s) for s in VECTORS[2][:2])
        self.assertEqual(pair(tx, rx[:4])["status"], "PARTIAL")
        self.assertEqual(pair(tx, b"")["status"], "TIMEOUT")
        self.assertEqual(decode(bytes(257), False)["status"], "LENGTH_ERROR")
        self.assertEqual(decode(bytes.fromhex("01030400019985"), False)["status"], "LENGTH_ERROR")
        self.assertEqual(decode(bytes.fromhex("01100000000202000167d4"), True)["status"], "LENGTH_ERROR")

    def test_boundary_quantities_and_unknown(self):
        maximum = decode(bytes.fromhex("0101000007d03fa6"), True)
        self.assertEqual((maximum["status"], maximum["quantity"]), ("OK", 2000))
        request = decode(bytes.fromhex("014100000001fc05"), True)
        self.assertEqual(request["status"], "UNKNOWN_FUNCTION")
        self.assertTrue(request["crc_ok"])
        exception = pair(bytes.fromhex("014100000001fc05"), bytes.fromhex("01c101b050"))
        self.assertTrue(exception["matched"])
        self.assertEqual(exception["status"], "EXCEPTION")
        self.assertEqual(exception["rx"]["exception_code"], 1)

    def test_exception_and_mismatch(self):
        tx = bytes.fromhex(VECTORS[2][0])
        exception = pair(tx, bytes.fromhex("018302c0f1"))
        self.assertTrue(exception["matched"])
        self.assertEqual(exception["status"], "EXCEPTION")
        self.assertEqual(exception["rx"]["exception_code"], 2)
        wrong = pair(bytes.fromhex(VECTORS[4][0]), bytes.fromhex("010500000000cdca"))
        self.assertEqual(wrong["status"], "MISMATCH")


class Window(unittest.TestCase):
    def test_real_modbus_inspector(self):
        self.assertTrue(os.environ.get("DISPLAY"), "A real WSLg display is required")
        import tkinter as tk
        from vel_gui_workbench import Workbench

        root = tk.Tk()
        root.geometry("1220x850+35+35")
        app = Workbench(root)
        root.geometry("1220x850+35+35")
        operations = [(1, 1, 0, "8"), (2, 1, 0, "4"), (3, 1, 0, "2"), (4, 1, 6, "2"),
                      (5, 1, 0, "1"), (5, 1, 0, "0"), (6, 1, 1, "20"),
                      (15, 1, 0, "1,0,1,0,0,0,0,0"), (16, 1, 0, "1,10,500"),
                      (3, 2, 0, "1"), (1, 1, 0, "8")]
        failures = []
        folder = None
        child = None
        stage = -2
        screenshots = os.environ.get("VEL_RTU_SCREENSHOT")
        deadline = time.monotonic() + 145

        def check():
            nonlocal stage, folder, child
            try:
                self.assertLess(time.monotonic(), deadline, app.status.get())
                if stage == -2 and app.available is not None:
                    app.select("Modbus")
                    self.assertEqual(str(app.start_button["state"]), "normal")
                    app.start_button.invoke()
                    child = app.job.pid
                    folder = app.folder
                    stage = -1
                elif stage == -1 and app.live:
                    app.input_mask.set("5")
                    app.inject_input()
                    stage = 0
                elif stage == 0 and app.live and not app.pending:
                    self.assertEqual(app.last_snapshot["inputs"], [True, False, True, False])
                    self.assertEqual(app.last_snapshot["registers"][6], 5)
                    stage = 1
                if 1 <= stage <= len(operations) and app.live and not app.pending:
                    fc, unit, address, value = operations[stage - 1]
                    panel = app.inspector
                    panel.choice.set(next(item for item, code in panel.functions.items() if code == fc))
                    panel.change()
                    for key, val in (("unit", unit), ("address", address), ("argument", value)):
                        panel.inputs[key][1].set(str(val))
                    panel.send_button.invoke()
                    stage += 1
                elif stage == len(operations) + 1 and app.live and not app.pending:
                    panel = app.inspector
                    self.assertTrue(panel.rows)
                    candidates = [i for i, row in panel.rows.items() if row["tx"]["function_code"] == 16]
                    self.assertEqual(len(candidates), 1)
                    panel.list.selection_set(candidates[0])
                    panel.list.see(candidates[0])
                    panel.show_selected()
                    self.assertIn("TX  01 10 00 00 00 03 06 00 01 00 0A 01 F4 FB 55", panel.raw.get())
                    self.assertIn("RX  01 10 00 00 00 03 80 08", panel.raw.get())
                    details = [panel.detail.item(i, "values") for i in panel.detail.get_children()]
                    self.assertTrue(any(row[0] == "TX" and row[1] == "11" and "500" in row[-1]
                                        for row in details), details)
                    if screenshots:
                        root.update_idletasks()
                        window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid",
                                                          str(os.getpid()), "--name", "VirtualEmbeddedLab"], text=True)
                        subprocess.run(["import", "-window", window.splitlines()[-1], screenshots],
                                       check=True, timeout=12)
                    app.close()
                    stage += 1
                    return
            except Exception as error:
                failures.append(error)
                app.close()
                return
            root.after(100, check)

        root.after(100, check)
        root.mainloop()
        if failures:
            raise failures[0]
        self.assertEqual(stage, len(operations) + 2)
        print(f"WSLg inspector session {folder}", flush=True)
        reports = [json.loads(line) for line in (folder / "rtu-transactions.jsonl").read_text().splitlines()]
        wire = [json.loads(line) for line in (folder / "rtu-wire.jsonl").read_text().splitlines()]
        flat = [(item["sequence"], direction, item[direction]["raw_hex"]) for item in reports
                for direction in ("tx", "rx") if item[direction]["byte_length"]]
        self.assertEqual(flat, [(item["sequence"], item["direction"], item["hex"]) for item in wire])
        self.assertEqual([x["sequence"] for x in reports], list(range(1, len(reports) + 1)))
        timed_out = [item for item in reports if item["status"] != "PASS"]
        self.assertEqual(len(timed_out), 1, [(x["sequence"], x["status"]) for x in timed_out])
        self.assertEqual(timed_out[0]["status"], "TIMEOUT")
        self.assertEqual(timed_out[0]["tx"]["slave_id"], 2)
        self.assertEqual(timed_out[0]["rx"]["byte_length"], 0)
        passed = [item for item in reports if item["status"] == "PASS"]
        self.assertEqual({item["tx"]["function_code"] for item in passed}, {1, 2, 3, 4, 5, 6, 15, 16})
        self.assertTrue(all(item["matched"] and item["tx"]["crc_ok"] and item["rx"]["crc_ok"]
                            and item["latency_ms"] <= 150 for item in passed))
        log = (folder / "slave.log").read_text()
        self.assertIn("INPUT bits=5", log)
        supervisor = json.loads((folder / "result.json").read_text())
        slave = json.loads((folder / "slave-exit.json").read_text())
        self.assertEqual(supervisor["status"], "CANCELLED")
        self.assertEqual(slave["exit"], 0)
        for pid in (supervisor["pid"], slave["pid"], child):
            self.assertFalse(Path(f"/proc/{pid}").exists())
        for path in re.findall(r"/dev/pts/\d+", log)[:2]:
            self.assertFalse(Path(path).exists(), path)
        if trace := os.environ.get("VEL_PTY_TRACE"):
            pty = int(re.findall(r"/dev/pts/(\d+)", log)[1])
            native = [json.loads(line) for line in Path(trace).read_text().splitlines()]
            raw = [row for row in native if row["pty"] == pty]
            for item in reports:
                bounded = [row for row in raw
                           if item["tx_ns"] <= row["ns"] <= item["finished_ns"]]
                for direction, frame in (("rx", item["tx"]), ("tx", item["rx"])):
                    actual = "".join(row["hex"] for row in bounded if row["dir"] == direction)
                    self.assertEqual(actual, frame["raw_hex"], (item["sequence"], direction))
            print("Independent native_sim libc PTY trace matches every host frame")
        print(f"{len(passed)} valid RTU pairs, {len(timed_out)} intentional timeout, cleanup verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
