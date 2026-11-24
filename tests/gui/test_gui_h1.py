"""Repeatable GUI-H1 acceptance against the real WSLg window and RTU slave."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_env import tool_environment, work
from vel_gui_features import BY_ID, CATEGORIES, FEATURES, capabilities, dependencies_for, invocation
from vel_jobs import workspace_lock

ENV = tool_environment()


class Registry(unittest.TestCase):
    def test_whitelist_and_dependencies(self):
        flags = {s: True for f in FEATURES for s in f.dependencies}
        self.assertEqual(len(BY_ID), len(FEATURES))
        for f in FEATURES:
            self.assertIn(f.category, CATEGORIES)
            self.assertTrue(f.modes or f.unavailable)
            for mode in f.modes:
                cmd = invocation(f.id, mode, ROOT, flags)
                self.assertTrue(Path(cmd[1]).is_file())
                self.assertEqual(cmd[0], sys.executable)
                with self.assertRaises(ValueError):
                    invocation(f.id, mode + "; arbitrary", ROOT, flags)
                if dependencies_for(f, mode):
                    with self.assertRaises(ValueError):
                        invocation(f.id, mode, ROOT, {})
        self.assertFalse(BY_ID["micro"].modes)
        self.assertFalse(BY_ID["history"].modes)

    def test_invalid_modbus_parameters(self):
        for command in ({"op":"write","index":8,"value":True},
                        {"op":"write","index":"0; echo bad","value":True},
                        {"op":"write","index":True,"value":True},
                        {"op":"input","mask":16}, {"op":"read","extra":1}):
            code = ("import json,sys; from vel_gui_modbus import validate; "
                    "validate(json.loads(sys.argv[1]))")
            result = subprocess.run([sys.executable, "-c", code, json.dumps(command)],
                                    cwd=ROOT / "scripts", env=ENV, capture_output=True, timeout=8)
            self.assertIn(b"ValueError: Unsupported or invalid", result.stderr)


class Lifecycle(unittest.TestCase):
    def job(self, folder, timeout=7, mode="单项实验", feature="arm"):
        return [sys.executable, ROOT / "scripts/vel_gui_job.py", feature, mode,
                folder, "--timeout", str(timeout)]

    def test_exit_success_and_rejected_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            ok = subprocess.run(self.job(folder), cwd=ROOT, env=ENV, capture_output=True, timeout=20)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads((folder/"result.json").read_text())["status"], "PASS")
            failed = subprocess.run(self.job(folder, mode="invalid"), cwd=ROOT, env=ENV,
                                    capture_output=True, timeout=20)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(json.loads((folder/"result.json").read_text())["status"], "UNAVAILABLE")

    def test_failed_job_reaps_separate_session(self):
        # Run the real supervisor with an injected test-only resolver. The
        # production CLI cannot select arbitrary commands.
        code = r"""
from argparse import Namespace
from pathlib import Path
import subprocess,sys
from vel_gui_job import run
def fixture(*_):
    worker = "import subprocess,sys; p=subprocess.Popen(['sleep','60'],start_new_session=True); print(p.pid,flush=True); sys.exit(11)"
    return [sys.executable, "-c", worker]
sys.exit(run(Namespace(feature="arm",mode="single",folder=Path(sys.argv[1]),timeout=5),resolve=fixture))
"""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            execution = subprocess.run([sys.executable, "-c", code, folder], cwd=ROOT/"scripts",
                                       env=ENV, capture_output=True, timeout=20, text=True)
            self.assertEqual(execution.returncode, 11, execution.stderr)
            data = json.loads((folder/"result.json").read_text())
            self.assertEqual(data["status"], "FAIL")
            self.assertFalse(Path("/proc", execution.stdout.splitlines()[0]).exists())

    def test_lock_conflict(self):
        lock = work("gui-h1/locks") / "arm.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory, workspace_lock(lock):
            folder = Path(directory)
            busy = subprocess.run(self.job(folder), cwd=ROOT, env=ENV, capture_output=True, timeout=20)
            self.assertEqual(busy.returncode, 75, busy.stderr)
            self.assertEqual(json.loads((folder/"result.json").read_text())["status"], "BUSY")

    def test_timeout_without_killing_unrelated_process(self):
        alive = subprocess.Popen(["sleep", "45"], start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                timed = subprocess.run(self.job(folder, 1, "交互会话", "rtu"),
                                       stdin=subprocess.PIPE, cwd=ROOT, env=ENV,
                                       capture_output=True, timeout=23)
                self.assertEqual(timed.returncode, 124, timed.stderr)
                result = json.loads((folder/"result.json").read_text())
                self.assertEqual(result["status"], "TIMEOUT")
                self.assertFalse(Path("/proc", str(result["pid"])).exists())
                self.assertIsNone(alive.poll())
        finally:
            alive.terminate()
            alive.wait(5)


class Graphical(unittest.TestCase):
    def test_real_wslg_and_rtu_gpio(self):
        import tkinter as tk
        from vel_gui_workbench import Workbench

        root = tk.Tk()
        root.geometry("900x600")
        window = Workbench(root)
        start = time.monotonic()
        phase = 0
        failure = []
        def check():
            nonlocal phase
            try:
                self.assertLess(time.monotonic()-start, 155, window.status.get())
                if phase == 0 and window.available is not None:
                    for category in CATEGORIES:
                        window.select(category)
                        root.update_idletasks()
                    window.select("Modbus")
                    self.assertEqual(window.feature.id, "rtu")
                    self.assertEqual(window.table.set("coils", "value"), "N/A")
                    self.assertIn("HISTORY", window.history.get())
                    self.assertEqual(window.mode.get(), "交互会话")
                    self.assertEqual(str(window.start_button["state"]), "normal")
                    window.start_button.invoke()
                    owned = window.job
                    window.start()
                    self.assertIs(window.job, owned)
                    phase = 1
                elif phase == 1 and window.live:
                    self.assertEqual(window.last_snapshot["coils"][0], False)
                    self.assertIn("LIVE", window.state.get())
                    window.ops[0].invoke()
                    phase = 2
                elif phase == 2 and window.live and not window.pending:
                    self.assertEqual(window.last_snapshot["coils"][0], True)
                    self.assertEqual(window.last_snapshot["registers"][7], 1)
                    self.assertTrue(window.table.set("coils","value").startswith("1"))
                    window.ops[1].invoke()
                    phase = 3
                elif phase == 3 and window.live and not window.pending:
                    self.assertEqual(window.last_snapshot["coils"][0], False)
                    self.assertEqual(window.last_snapshot["registers"][7], 0)
                    window.input_mask.set("5")
                    window.ops[3].invoke()
                    phase = 4
                elif phase == 4 and window.live and not window.pending:
                    self.assertEqual(window.last_snapshot["inputs"], [True,False,True,False])
                    self.assertEqual(window.last_snapshot["registers"][6], 5)
                    window.select(CATEGORIES[-1])
                    window.log_source.set("rtu-wire.jsonl")
                    phase = 5
                elif phase == 5:
                    self.assertIn('"direction"', window.log_box.get("1.0","end"))
                    print("WSLg session", window.folder, flush=True)
                    window.close()
                    phase = 6
                    return
            except Exception as error:
                failure.append(error)
                window.close()
                return
            root.after(160,check)
        root.after(180,check)
        root.mainloop()
        if failure:
            raise failure[0]
        self.assertEqual(phase,6)
        result=json.loads((window.folder/"result.json").read_text())
        self.assertEqual(result["status"],"CANCELLED")
        slave=json.loads((window.folder/"slave-exit.json").read_text())
        self.assertFalse(Path("/proc",str(slave["pid"])).exists())
        frames=[json.loads(line) for line in (window.folder/"rtu-wire.jsonl").read_text().splitlines()]
        sent=[x["hex"][:12] for x in frames if x["direction"]=="tx"]
        for request in ("01050000ff00","010500000000","010100000008","010200000004",
                        "010300000008","010400000008"):
            self.assertIn(request,sent)
        self.assertIn("INPUT bits=5",(window.folder/"slave.log").read_text())
        self.assertTrue(any(x["direction"]=="rx" for x in frames))
        self.assertFalse(Path("/proc",str(result["pid"])).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
