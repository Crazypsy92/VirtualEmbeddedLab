#!/usr/bin/env python3
"""Build and exercise the restored Stage 8.3 gateway in the current WSL."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time

from vel_jobs import BusyWorkspace, install_cancel_handlers, workspace_lock
from vel_env import ROOT, nonroot, tool_environment, work


def run_step(script, args, env, directory, timeout):
    command = [sys.executable, ROOT / "scripts" / script, *args]
    log = directory / (Path(script).stem + ".log")
    started = time.monotonic()
    print(f"开始 {script}，日志 {log}", flush=True)
    with log.open("w") as output:
        print(shlex.join(map(str, command)), file=output, flush=True)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = process.wait(timeout)
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(5)
            if not isinstance(error, subprocess.TimeoutExpired):
                raise
            rc = 124
    print(f"{script}: exit {rc}, log {log}", flush=True)
    if rc:
        print(log.read_text(errors="replace")[-3000:], flush=True)
    return {"exit": rc, "seconds": time.monotonic() - started, "log": str(log)}


def main():
    nonroot()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["build", "protocol", "concurrency", "fault", "all"],
                        default="all")
    parser.add_argument("--historical", action="store_true",
                        help="also run the real Stage 8.2 and earlier regression")
    args = parser.parse_args()
    workspace = work("gateway_stage8_3_ws")
    workspace.mkdir(parents=True, exist_ok=True)
    with workspace_lock(workspace / "accept.lock"):
        out = Path(os.environ["VEL_STAGE8_3_EVIDENCE"]) if "VEL_STAGE8_3_EVIDENCE" in os.environ else (
            Path(tempfile.mkdtemp(prefix="accept-", dir=workspace)))
        out.mkdir(parents=True, exist_ok=True)
        env = tool_environment()
        env["VEL_STAGE8_3_EVIDENCE"] = str(out)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            env["VEL_GATEWAY_PORT"] = str(listener.getsockname()[1])
        commands = [("stage8_3_build.py", [], 360), ("stage8_2_build.py", [], 360)]
        if args.mode != "build":
            commands.append(("stage8_3_test.py", ["--mode", args.mode], 240))
        if args.mode == "all":
            commands.append(("stage8_3_consistency.py", [], 35))
        if args.historical and args.mode == "all":
            env["VEL_STAGE8_2_EVIDENCE"] = str(out / "historical")
            commands.append(("accept_stage8_2.py", ["--mode", "all"], 4800))
        report = {"status": "IN_PROGRESS", "mode": args.mode, "steps": {},
                  "historical_requested": args.historical, "hardware": "NOT TESTED"}

        def save():
            (out / "acceptance.json").write_text(json.dumps(report, indent=2) + chr(10))

        save()
        try:
            for script, options, timeout in commands:
                result = run_step(script, options, env, out, timeout)
                report["steps"][script] = result
                if result["exit"]:
                    report["status"] = "FAIL"
                    return result["exit"]
                save()
            report["status"] = "Stage 8.3 SOFTWARE PASS" if args.historical else "PASS"
            print(out / "acceptance.json")
            return 0
        except (KeyboardInterrupt, SystemExit):
            report["status"] = "CANCELLED"
            raise
        finally:
            save()


if __name__ == "__main__":
    install_cancel_handlers()
    try:
        sys.exit(main())
    except BusyWorkspace as error:
        print(error, file=sys.stderr)
        sys.exit(75)
