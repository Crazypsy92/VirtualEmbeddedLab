"""Audit one-shot RTU faults against native_sim and exercise real WSLg controls."""
from collections import Counter
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from tempfile import mkdtemp
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_env import tool_environment, work
from vel_jobs import lock_status
from vel_rtu_fault_rules import RULES, adu, changes, original_request, request_bytes, response_bytes
from vel_rtu_frames import decode, pair


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def folder_for(prefix):
    base = work("rtu-h3-test")
    base.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix=prefix + "-", dir=base))


def audit_events(folder):
    return rows(folder / "rtu-faults.jsonl") if (folder / "rtu-faults.jsonl").is_file() else []


def confirm_cleanup(test, folder, supervisor):
    result = json.loads((folder / "result.json").read_text())
    slave = json.loads((folder / "slave-exit.json").read_text())
    ptys = set(re.findall(r"/dev/pts/\d+", (folder / "slave.log").read_text()))
    test.assertEqual(len(ptys), 2)
    for pid in (slave["pid"], supervisor, result["pid"]):
        test.assertFalse(Path(f"/proc/{pid}").exists())
    test.assertTrue(all(not Path(p).exists() for p in ptys))
    test.assertFalse(lock_status(work("gui-h1/locks") / "rtu.lock")[0])
    return result


def start_supervisor(folder, tracer=None, timeout=None):
    env = tool_environment()
    if tracer is not None:
        env.update(LD_PRELOAD=str(tracer), VEL_PTY_TRACE=str(folder / "slave-pty.jsonl"))
    command = [sys.executable, ROOT / "scripts/vel_gui_job.py", "rtu", "交互会话", folder]
    if timeout is not None:
        command += ["--timeout", str(timeout)]
    with (folder / "test-console.log").open("w") as out:
        return subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)


class Rules(unittest.TestCase):
    def test_crc_corruption_cannot_match_in_twenty_combinations(self):
        tx = bytes.fromhex("010300000001840a")
        for value in range(10):
            rx = adu(bytes((1, 3, 2, 0, value)))
            self.assertEqual(pair(tx, rx)["status"], "PASS")
            self.assertEqual(pair(tx, response_bytes("rx_crc", rx))["status"], "CRC_ERROR")
            self.assertFalse(pair(request_bytes("tx_crc", tx), rx)["matched"])

    def test_mutations_and_unchanged_boundaries(self):
        holding = [1, 10, 500, 0, 100, 0, 0, 0]
        for name, rule in RULES.items():
            with self.subTest(name=name):
                original = original_request(name, holding)
                incoming = bytes.fromhex("010600030001b80a")
                requested, forwarded = request_bytes(name, original), response_bytes(name, incoming)
                self.assertTrue(decode(original, True)["crc_ok"])
                if rule.direction == "tx":
                    self.assertTrue(changes(original, requested))
                    self.assertEqual(incoming, forwarded)
                else:
                    self.assertEqual(original, requested)
                    self.assertTrue(changes(incoming, forwarded))
                if name in ("tx_unit", "tx_function", "tx_address", "tx_value"):
                    self.assertTrue(decode(requested, True)["crc_ok"])


class Native(unittest.TestCase):
    def test_sixty_faults_and_real_byte_recovery(self):
        folder = folder_for("native")
        tracer = folder / "trace_pty.so"
        subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        ROOT / "host/modbus_master/trace_pty.c", "-o", tracer, "-ldl"], check=True, timeout=20)
        process = start_supervisor(folder, tracer)
        plan = [name for name in RULES for _ in range(10 if name.endswith("_crc") else 5)]
        commands = b"".join((json.dumps({"op": "fault", "rule": name}) + "\n").encode() for name in plan)
        try:
            process.communicate(commands, timeout=155)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(12)
        print(f"Native H3 evidence {folder}", flush=True)
        self.assertEqual(process.returncode, 0, (folder / "test-console.log").read_text()[-5000:])
        self.assertEqual(confirm_cleanup(self, folder, process.pid)["status"], "COMPLETED")
        audit = audit_events(folder)
        inject = [row for row in audit if row["kind"] == "injection"]
        recovery = [row for row in audit if row["kind"] == "recovery"]
        records = {row["sequence"]: row for row in rows(folder / "rtu-transactions.jsonl")}
        socket = int(re.findall(r"/dev/pts/(\d+)", (folder / "slave.log").read_text())[1])
        wire = [row for row in rows(folder / "slave-pty.jsonl") if row["pty"] == socket]
        self.assertEqual([row["rule"] for row in inject], plan)
        self.assertEqual([row["rule"] for row in recovery], plan)
        for mutation, recovered, rule_name in zip(inject, recovery, plan):
            seq = mutation["sequence"]
            rule = RULES[rule_name]
            self.assertEqual(mutation["status"], rule.status, mutation)
            self.assertEqual(mutation["observed_exception"], rule.exception, mutation)
            self.assertTrue(all(recovered[key] for key in ("expectation_met", "recovered", "state_unchanged")))
            self.assertEqual(recovered["recovery_sequence"], seq + 1)
            self.assertEqual(records[seq + 1]["status"], "RECOVERED")
            self.assertEqual(records[seq + 1]["pre_tx_rx_hex"], "")
            frame = records[seq]
            physical = [event for event in wire if frame["monotonic_ns"] <= event["ns"] <= frame["finished_ns"]]
            for direction, key in (("rx", "slave_rx_hex"), ("tx", "slave_tx_hex")):
                observed = "".join(event["hex"] for event in physical if event["dir"] == direction)
                self.assertEqual(observed, mutation[key], (seq, direction))
            if rule.exception:
                self.assertEqual(frame["rx"]["function_code"], frame["tx"]["function_code"] | 0x80)
                self.assertTrue(frame["rx"]["crc_ok"])
            if rule.direction == "rx":
                self.assertEqual(mutation["slave_rx_hex"], mutation["original_tx_hex"])
                self.assertTrue(mutation["slave_response_crc_ok"])
            else:
                self.assertEqual(mutation["slave_tx_hex"], mutation["master_rx_hex"])
            if rule_name == "tx_crc":
                self.assertFalse(frame["tx"]["crc_ok"])
            if rule_name == "rx_crc":
                self.assertFalse(frame["rx"]["crc_ok"])
                self.assertFalse(frame["matched"])
            if rule_name == "rx_delay":
                self.assertEqual(mutation["quarantined_hex"], mutation["slave_tx_hex"])
                self.assertGreater(mutation["quarantine_ns"], mutation["host_deadline_ns"])
                self.assertEqual(mutation["master_rx_hex"], "")
        print(f"{len(recovery)} recovery successes, statuses {dict(Counter(row['status'] for row in inject))}", flush=True)

    def test_unexpected_slave_exit_and_active_timeout_cleanup(self):
        # Start with a live session and stop only its identified native_sim child.
        for scenario in ("slave_exit", "supervisor_timeout"):
            with self.subTest(scenario=scenario):
                folder = folder_for(scenario)
                process = start_supervisor(folder, timeout=80 if scenario == "supervisor_timeout" else None)
                started = time.monotonic()
                child = None
                try:
                    while time.monotonic() - started < 125 and process.poll() is None:
                        log = (folder / "test-console.log").read_text(errors="replace")
                        for line in log.splitlines():
                            if line.startswith('{"event": "slave_started"'):
                                child = json.loads(line)["pid"]
                        if '"event": "ready"' in log:
                            break
                        time.sleep(.04)
                    self.assertIn('"event": "ready"', log)
                    if scenario == "slave_exit":
                        os.kill(child, signal.SIGKILL)
                        process.wait(10)
                        errors = [json.loads(l).get("reason", "") for l in
                                  (folder / "test-console.log").read_text().splitlines() if l.startswith("{")]
                        self.assertTrue(any("从站在会话期间退出" in error for error in errors), errors)
                    else:
                        process.stdin.write(b'{"op":"fault","rule":"rx_delay"}\n')
                        process.stdin.flush()
                        self.assertEqual(process.wait(95), 124)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(12)
                    process.stdin.close()
                self.assertEqual(confirm_cleanup(self, folder, process.pid)["status"],
                                 "FAIL" if scenario == "slave_exit" else "TIMEOUT")
                print(f"{scenario} cleanup evidence {folder}", flush=True)


class Window(unittest.TestCase):
    def test_real_gui_fault_controls_recovery_and_cancel_repeat(self):
        self.assertTrue(os.environ.get("DISPLAY"))
        import tkinter as tk
        from vel_gui_workbench import Workbench
        root = tk.Tk()
        app = Workbench(root)
        root.geometry("1260x920+20+20")
        stage = 0
        sequence = 0
        errors = []
        folder = None
        supervisor = None
        deadline = time.monotonic() + 145
        plan = ("rx_crc", "tx_address", "rx_delay", "tx_drop")

        def trigger(ui, name, count):
            ui.direction.set("主站 → 从站" if RULES[name].direction == "tx" else "从站 → 主站")
            ui.update_presets()
            ui.preset.set(RULES[name].label)
            ui.count.set(str(count))
            ui.start.invoke()

        def check():
            nonlocal stage, sequence, folder, supervisor
            try:
                self.assertLess(time.monotonic(), deadline, (stage, app.status.get()))
                if stage == 0 and app.available is not None:
                    app.select("Modbus")
                    app.start_button.invoke()
                    folder, supervisor = app.folder, app.job.pid
                    stage = 1
                elif stage == 1 and app.live and not app.pending:
                    ui = app.inspector.faults
                    ui.open.set(True)
                    ui.toggle()
                    trigger(ui, plan[0], 1)
                    stage = 2
                elif 2 <= stage <= 5 and app.live and not app.pending:
                    done = [row for row in audit_events(folder) if row["kind"] == "recovery"]
                    if len(done) <= sequence:
                        root.after(100, check)
                        return
                    sequence = len(done)
                    latest = done[-1]
                    name = plan[stage - 2]
                    self.assertEqual(latest["rule"], name)
                    panel = app.inspector
                    row = panel.rows[str(latest["sequence"])]
                    self.assertEqual(row["status"], RULES[name].status)
                    self.assertEqual(panel.rows[str(latest["recovery_sequence"])]["status"], "RECOVERED")
                    self.assertIn("RECOVERED", panel.faults.status.get())
                    layers = panel.layers
                    panel.list.selection_set(str(latest["sequence"]))
                    panel.show_selected()
                    layers.tabs.select(layers.injection_tab)
                    self.assertEqual(len(layers.injection.get_children()), 4)
                    if name == "rx_crc":
                        layers.edits.selection_set(layers.edits.get_children()[0])
                        layers.open_fault_byte()
                        self.assertTrue(layers.hex_view.tag_ranges("highlight"))
                        layers.tabs.select(layers.injection_tab)
                    if (target := os.environ.get("VEL_H3_SCREENSHOTS")) and stage <= 4:
                        root.update()
                        root.after(100)
                        root.update()
                        subprocess.run(["import", "-window", hex(root.winfo_id()),
                                        str(Path(target) / f"{name}.png")], check=True, timeout=12)
                    if stage < 5:
                        trigger(panel.faults, plan[stage - 1], 1 if stage < 4 else 5)
                    stage += 1
                if stage == 5 and app.pending and app.inspector.faults.running:
                    app.inspector.faults.stop.invoke()
                if stage == 6:
                    app.close()
                    stage += 1
                    return
            except Exception as error:
                errors.append(error)
                app.close()
                return
            root.after(80, check)

        root.after(80, check)
        root.mainloop()
        if errors:
            raise errors[0]
        self.assertEqual(stage, 7)
        self.assertEqual([x["rule"] for x in audit_events(folder) if x["kind"] == "recovery"], list(plan))
        self.assertEqual(confirm_cleanup(self, folder, supervisor)["status"], "CANCELLED")
        print(f"WSLg H3 evidence {folder}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
