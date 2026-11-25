"""Verify I2C worker bindings headlessly and through the actual WSLg workbench."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from vel_env import tool_environment, work
from vel_jobs import lock_status


def records(folder):
    return [json.loads(line) for line in (folder / "i2c-transactions.jsonl").read_text(encoding="utf-8").splitlines()]


def result(folder):
    return json.loads((folder / "result.json").read_text())


class Headless(unittest.TestCase):
    def test_worker_scan_batch_and_validation(self):
        root = work("i2c-headless")
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=root))
        messages = [{"op": "scan", "khz": 400}]
        for address, repeat in [(0x28, 3), (0x80, 2)]:
            messages.append({"op": "transfer", "repeat": repeat,
                             "request": {"address": address, "operation": "register-read", "khz": 400}})
        args = [sys.executable, ROOT / "scripts/vel_gui_job.py", "i2c", "Host I2C", folder, "--timeout", "15"]
        client = subprocess.run(args, input="".join(json.dumps(x) + "\n" for x in messages),
                                capture_output=True, env=tool_environment(), text=True, timeout=20)
        self.assertEqual(client.returncode, 0, client.stdout + client.stderr)
        events = [json.loads(line) for line in client.stdout.splitlines() if line.startswith("{")]
        self.assertEqual([event["event"] for event in events],
                         ["i2c_ready", "i2c_result", "i2c_result", "i2c_invalid"])
        scan = events[1]
        self.assertEqual(scan["found"], ["0x28", "0x50"])
        self.assertEqual(scan["status"], {"OK": 2, "NACK": 110})
        rows = records(folder)
        self.assertEqual(len(rows), scan["count"] + 3)
        self.assertEqual([r["sequence"] for r in rows], list(range(1, 116)))
        self.assertEqual([r["data"] for r in rows[-3:]], ["00"] * 3)
        self.assertTrue(all(row["scope"] == "SIMULATED" and row["period_ns"] == 2500 for row in rows))
        child = result(folder)
        self.assertEqual(child["status"], "COMPLETED")
        self.assertFalse(Path(f"/proc/{child['pid']}").exists())
        self.assertFalse(lock_status(work("gui-h1/locks") / "i2c.lock")[0])


class Window(unittest.TestCase):
    def test_native_scan_read_write_and_waveform(self):
        self.assertTrue(os.environ.get("DISPLAY"), "A WSLg display is required")
        import tkinter as tk
        from vel_gui_workbench import Workbench

        root = tk.Tk()
        app = Workbench(root)
        root.geometry("1280x940+10+10")
        deadline = time.monotonic() + 160
        stage, folder, supervisor = 0, None, None
        failures = []

        def capture(name):
            path = os.environ.get("VEL_I2C_EVIDENCE")
            if path:
                root.update()
                root.after(120)
                root.update()
                subprocess.run(["import", "-window", hex(root.winfo_id()), str(Path(path) / f"{name}.png")],
                               check=True, timeout=12)

        def check():
            nonlocal folder, stage, supervisor
            try:
                self.assertLess(time.monotonic(), deadline, (stage, app.status.get()))
                if stage == 0 and app.available is not None:
                    app.select("I2C")
                    self.assertEqual(app.mode.get(), "Zephyr I2C")
                    app.start_button.invoke()
                    self.assertIsNotNone(app.job)
                    folder, supervisor = app.folder, app.job.pid
                    stage = 1
                elif stage == 1 and app.live:
                    panel = app.i2c_panel
                    self.assertIn("zephyr-i2c-emul", panel.connected.get())
                    panel.operations[0].invoke()
                    stage = 2
                elif stage == 2 and not app.pending and len(app.i2c_panel.records) >= 112:
                    panel = app.i2c_panel
                    self.assertIn("0x28、0x50", panel.notice.get())
                    capture("i2c-scan")
                    panel.entries["operation"].set("寄存器写")
                    panel.entries["data"].set("AB CD")
                    panel.send_button.invoke()
                    stage = 3
                elif stage == 3 and not app.pending and len(app.i2c_panel.records) >= 113:
                    panel = app.i2c_panel
                    panel.entries["operation"].set("寄存器读")
                    panel.entries["length"].set("2")
                    panel.send_button.invoke()
                    stage = 4
                elif stage == 4 and not app.pending and len(app.i2c_panel.records) >= 114:
                    panel = app.i2c_panel
                    self.assertEqual(panel.records["114"]["data"], "abcd")
                    panel.operations[5].invoke()
                    panel.entries["khz"].set("400")
                    panel.send_button.invoke()
                    stage = 5
                elif stage == 5 and not app.pending and len(app.i2c_panel.records) >= 115:
                    panel = app.i2c_panel
                    self.assertEqual(panel.records["115"]["data"], "ffff")
                    panel.history.selection_set("115")
                    panel.history.see("115")
                    panel.select()
                    fields = [panel.fields.item(i, "values") for i in panel.fields.get_children()]
                    self.assertIn(("Repeated START",), fields)
                    self.assertEqual(fields[4][3], "A1")
                    self.assertIn("主机 NACK", fields[-2][5])
                    capture("i2c-fields")
                    panel.tabs.select(panel.wave_tab)
                    root.update()
                    panel.draw()
                    self.assertIn("2.5 µs", panel.wave_label.get())
                    self.assertTrue(panel.canvas.find_all())
                    capture("i2c-waveform")
                    panel.fields.selection_set("4")
                    panel.whole.set(False)
                    panel.draw()
                    capture("i2c-selected-byte")
                    panel.entries["address"].set("80")
                    panel.send_button.invoke()
                    self.assertIn("未发送", panel.notice.get())
                    self.assertEqual(len(records(folder)), 115)
                    export = folder / "gui-export.jsonl"
                    with patch("vel_i2c_panel.filedialog.asksaveasfilename", return_value=str(export)):
                        panel.export_button.invoke()
                    self.assertEqual(export.read_bytes(), (folder / "i2c-transactions.jsonl").read_bytes())
                    panel.clear()
                    self.assertFalse(panel.history.get_children())
                    self.assertEqual(len(records(folder)), 115)
                    app.stop.invoke()
                    stage = 6
                elif stage == 6 and not app.job:
                    self.assertIn("未连接", app.i2c_panel.connected.get())
                    app.close()
                    stage = 7
                    return
            except Exception as error:
                failures.append(error)
                app.close()
                return
            root.after(125, check)

        root.after(160, check)
        root.mainloop()
        if failures:
            raise failures[0]
        self.assertEqual(stage, 7)
        child = result(folder)
        self.assertEqual(child["status"], "CANCELLED")
        ready = next(json.loads(line) for line in (folder / "console.log").read_text().splitlines()
                     if line.startswith('{"event": "i2c_ready"'))
        for pid in (supervisor, child["pid"], ready["native_pid"]):
            self.assertFalse(Path(f"/proc/{pid}").exists(), pid)
        self.assertFalse(lock_status(work("gui-h1/locks") / "i2c.lock")[0])
        print(f"WSLg I2C evidence {folder}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
