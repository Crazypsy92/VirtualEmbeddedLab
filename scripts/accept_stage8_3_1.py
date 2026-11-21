#!/usr/bin/env python3
"""Run the restored gateway reliability suites with bounded execution."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile

from accept_stage8_3 import run_step
from vel_jobs import BusyWorkspace, install_cancel_handlers, workspace_lock
from vel_env import nonroot, tool_environment, work

LIMITS = {"tid": 120, "rtu-late": 45, "tcp-stream": 45,
          "stress": 900, "endurance": 1940, "recovery": 260}


def main():
    nonroot()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=[*LIMITS, "quick", "all"], default="quick")
    args = parser.parse_args()
    workspace = work("gateway_stage8_3_1_ws")
    workspace.mkdir(parents=True, exist_ok=True)
    with workspace_lock(workspace / "accept.lock"):
        out = Path(tempfile.mkdtemp(prefix="accept-", dir=workspace))
        env = tool_environment()
        env["VEL_STAGE8_3_1_EVIDENCE"] = str(out)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            env["VEL_GATEWAY_PORT"] = str(listener.getsockname()[1])
        modes = list(LIMITS) if args.mode == "all" else (
            ["tid", "rtu-late", "tcp-stream", "recovery"] if args.mode == "quick" else [args.mode])
        results = {"build": run_step("stage8_3_1_build.py", [], env, out, 360)}
        if not results["build"]["exit"]:
            for mode in modes:
                folder = out / ("runner-" + mode)
                folder.mkdir()
                results[mode] = run_step("stage8_3_1_tests.py", ["--mode", mode], env, folder, LIMITS[mode])
        rc = int(any(step["exit"] for step in results.values()))
        (out / "acceptance.json").write_text(json.dumps({"status": "FAIL" if rc else "PASS",
                                                        "steps": results}, indent=2) + chr(10))
        print(out / "acceptance.json")
        return rc


if __name__ == "__main__":
    install_cancel_handlers()
    try:
        sys.exit(main())
    except BusyWorkspace as error:
        print(error, file=sys.stderr)
        sys.exit(75)
