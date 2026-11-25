"""Run the same real native_sim protocol sequence through both serial backends."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

from test_rtu_h3 import ROOT, audit_events, confirm_cleanup, folder_for, rows, start_supervisor


def config(backend):
    return {"backend": backend, "simulation": True, "settings": {}}


class Protocols(unittest.TestCase):
    def exercise(self, backend):
        folder = folder_for("stage84-" + backend)
        (folder / "transport-request.json").write_text(json.dumps(config(backend)))
        worker = start_supervisor(folder)
        requests = [
            {"op": "protocol", "fc": 3, "unit": 1, "address": 1, "count": 1},
            {"op": "protocol", "fc": 6, "unit": 1, "address": 1, "values": [37]},
            {"op": "protocol", "fc": 3, "unit": 1, "address": 1, "count": 1},
            *({"op": "fault", "rule": rule} for rule in
              ("tx_crc", "rx_crc", "tx_drop", "tx_address", "rx_drop", "rx_delay")),
        ]
        try:
            worker.communicate("".join(json.dumps(x) + "\n" for x in requests).encode(), timeout=140)
        finally:
            if worker.poll() is None:
                worker.terminate()
                worker.wait(12)
        log = (folder / "test-console.log").read_text()
        print(f"Transport RTU {backend} evidence {folder}", flush=True)
        self.assertEqual(worker.returncode, 0, log[-4500:])
        summary = confirm_cleanup(self, folder, worker.pid)
        expected_scope = {"serial": "SERIAL_BACKEND_ON_PTY", "pty": "PTY_SIMULATION"}[backend]
        self.assertEqual(summary["transport"]["scope"], expected_scope)
        self.assertEqual(summary["transport"]["backend"], backend)
        self.assertFalse(summary["transport"]["connected"])
        events = [json.loads(line) for line in log.splitlines() if line.startswith("{")]
        results = [event for event in events if event["event"] == "protocol_result"]
        self.assertEqual([e["values"] for e in results], [[10], [37], [37]])
        self.assertIs(results[1]["verified"], True)
        audit = audit_events(folder)
        self.assertEqual([e["status"] for e in audit if e["kind"] == "injection"],
                         ["TIMEOUT", "CRC_ERROR", "TIMEOUT", "EXCEPTION", "TIMEOUT", "LATE_RESPONSE"])
        recoveries = [e for e in audit if e["kind"] == "recovery"]
        self.assertEqual(len(recoveries), 6)
        self.assertTrue(all(e["expectation_met"] and e["recovered"] and e["state_unchanged"] for e in recoveries))
        transactions = rows(folder / "rtu-transactions.jsonl")
        self.assertTrue(all(item["transport"]["scope"] == expected_scope for item in transactions))
        self.assertTrue(all(item["transport"]["backend"] == backend for item in transactions))

    def test_pty(self):
        self.exercise("pty")

    def test_serial_on_pty(self):
        self.exercise("serial")


class Window(unittest.TestCase):
    def test_real_wslg_select_probe_disconnect_and_no_fallback(self):
        self.assertTrue(os.environ.get("DISPLAY"), "WSLg display is required")
        import tkinter as tk
        from vel_gui_workbench import Workbench
        from vel_jobs import lock_status
        from vel_env import work
        root = tk.Tk()
        app = Workbench(root)
        root.geometry("1260x920+20+20")
        stage = 0
        failures = []
        runs = []
        deadline = time.monotonic() + 190

        def capture(name):
            path = os.environ.get("VEL_STAGE84_SCREENSHOTS")
            if path:
                root.update()
                root.after(100)
                root.update()
                subprocess.run(["import", "-window", hex(root.winfo_id()), str(Path(path) / f"{name}.png")],
                               check=True, timeout=12)

        def check():
            nonlocal stage
            try:
                self.assertLess(time.monotonic(), deadline, (stage, app.status.get()))
                if stage == 0 and app.available is not None:
                    app.select("Modbus")
                    panel = app.connection_panel
                    panel.expanded.set(True)
                    panel.show()
                    panel.connect_button.invoke()
                    runs.append((app.folder, app.job.pid))
                    stage = 1
                elif stage == 1 and app.live:
                    app.connection_panel.probe_button.invoke()
                    stage = 7
                elif stage == 7 and app.live and not app.pending:
                    panel = app.connection_panel
                    self.assertIn("PTY_SIMULATION", panel.message.get())
                    self.assertIn("FC03 通过", panel.message.get())
                    capture("pty-probe")
                    panel.disconnect_button.invoke()
                    stage = 8
                elif stage == 8 and not app.job:
                    panel = app.connection_panel
                    self.assertIn("未连接", panel.message.get())
                    self.assertEqual(confirm_cleanup(self, *runs[-1])["status"], "CANCELLED")
                    panel.backend.set("Serial 设备")
                    panel.change()
                    panel.fixture_control.invoke()
                    panel.connect_button.invoke()
                    runs.append((app.folder, app.job.pid))
                    stage = 2
                elif stage == 2 and app.live:
                    panel = app.connection_panel
                    self.assertIn("SERIAL_BACKEND_ON_PTY", panel.message.get())
                    self.assertIn("/dev/pts/", panel.message.get())
                    app.select("系统概览")
                    app.select("Modbus")
                    panel = app.connection_panel
                    self.assertEqual(panel.backend.get(), "Serial 设备")
                    self.assertTrue(panel.fixture.get())
                    self.assertIn("SERIAL_BACKEND_ON_PTY", panel.message.get())
                    panel.probe_button.invoke()
                    stage = 3
                elif stage == 3 and app.live and not app.pending:
                    self.assertIn("FC03 通过", app.connection_panel.message.get())
                    capture("serial-pty")
                    for event in rows(runs[-1][0] / "console.log"):
                        if event["event"] == "slave_started":
                            os.kill(event["pid"], signal.SIGKILL)
                            break
                    else:
                        self.fail("No owned simulator process")
                    stage = 4
                elif stage == 4 and not app.job:
                    panel = app.connection_panel
                    self.assertIn("SERIAL_BACKEND_ON_PTY", panel.message.get())
                    self.assertIn("退出", panel.message.get())
                    self.assertEqual(confirm_cleanup(self, *runs[-1])["status"], "FAIL")
                    capture("serial-disconnected")
                    panel.fixture_control.invoke()
                    panel.entries["port"].set("/dev/vel-stage84-port-not-connected")
                    panel.connect_button.invoke()
                    runs.append((app.folder, app.job.pid))
                    stage = 5
                elif stage == 5 and not app.job:
                    panel = app.connection_panel
                    self.assertIn("SERIAL_DEVICE", panel.message.get())
                    self.assertIn("/dev/vel-stage84-port-not-connected", panel.message.get())
                    self.assertIn("未连接", panel.message.get())
                    folder = runs[-1][0]
                    self.assertFalse((folder / "slave-build").exists())
                    verdict = json.loads((folder / "result.json").read_text())
                    self.assertEqual(verdict["status"], "FAIL")
                    self.assertFalse(verdict["transport"]["connected"])
                    self.assertIn("error", verdict["transport"])
                    self.assertFalse(Path(f"/proc/{verdict['pid']}").exists())
                    capture("missing-port")
                    self.assertFalse(lock_status(work("gui-h1/locks") / "rtu.lock")[0])
                    app.close()
                    stage = 6
                    return
            except Exception as error:
                failures.append(error)
                app.close()
                return
            root.after(120, check)

        root.after(150, check)
        root.mainloop()
        if failures:
            raise failures[0]
        self.assertEqual(stage, 6)
        for folder, _ in runs:
            print(f"WSLg Stage 8.4 evidence {folder}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
