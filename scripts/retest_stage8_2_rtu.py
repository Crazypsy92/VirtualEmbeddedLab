#!/usr/bin/env python3
"""Run five independent Stage 8.2 protocol sessions and the fault suite."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from audit_stage8_2_rtu import audit
from vel_env import ROOT, nonroot, tool_environment
from vel_jobs import install_cancel_handlers


def run(command, env, log, timeout):
    with log.open("w") as output:
        print(" ".join(map(str, command)), file=output, flush=True)
        process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True,
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            return process.wait(timeout)
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(6)
            except ProcessLookupError:
                process.wait()
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(5)
            if isinstance(error, subprocess.TimeoutExpired):
                return 124
            raise


def main():
    nonroot()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new output folder")
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    env = tool_environment()
    env["VEL_WORK_ROOT"] = str(folder / "work")
    env["VEL_STAGE8_2_EVIDENCE"] = str(folder / "build-report")
    report = {"status": "FAIL", "sessions": {}, "hardware": "NOT TESTED"}
    try:
        report["build_exit"] = run([sys.executable, ROOT / "scripts/accept_stage8_2.py",
                                    "--mode", "build"], env, folder / "build.log", 380)
        if report["build_exit"]:
            return 1
        ws = folder / "work/modbus_stage8_2_ws"
        report["elf_sha256"] = hashlib.sha256(
            (ws / "build/zephyr/zephyr.exe").read_bytes()).hexdigest()
        library = folder / "trace_pty.so"
        report["tracer_build_exit"] = run(
            ["gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
             ROOT / "host/modbus_master/trace_pty.c", "-o", library, "-ldl"],
            env, folder / "tracer-build.log", 30)
        if report["tracer_build_exit"]:
            return 1
        for name in [*(f"protocol-{i}" for i in range(1, 6)), "fault"]:
            mode = name.split("-")[0]
            out = folder / name
            out.mkdir()
            trace = out / "slave-pty.jsonl"
            session_env = env | {"VEL_STAGE8_2_EVIDENCE": str(out), "VEL_PTY_TRACE": str(trace)}
            session_env["LD_PRELOAD"] = " ".join(v for v in
                                                (str(library), env.get("LD_PRELOAD")) if v)
            existing = set((ws / "runs").glob("master-*"))
            start = time.monotonic()
            code = run([sys.executable, ROOT / "host/modbus_master/test_master.py", mode],
                       session_env, out / "command.log", 125)
            launches = sorted(set((ws / "runs").glob("master-*")) - existing)
            session = {"exit": code, "seconds": time.monotonic() - start,
                       "runs": [str(p) for p in launches], "status": "FAIL"}
            report["sessions"][name] = session
            try:
                if code == 0 and len(launches) == 1:
                    evidence = out / mode / "acceptance.json"
                    verdict = (audit(evidence, trace) if mode == "protocol"
                               else json.loads(evidence.read_text()))
                    session.update(verdict)
            except (OSError, ValueError, KeyError) as error:
                session["audit_error"] = str(error)
            (out / "result.json").write_text(json.dumps(session, indent=2) + "\n")
            print(name, session["status"], flush=True)
        if all(item["status"] == "PASS" for item in report["sessions"].values()):
            report["status"] = "PASS"
            return 0
        return 1
    finally:
        (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    install_cancel_handlers()
    sys.exit(main())
