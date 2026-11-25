#!/usr/bin/env python3
"""Run Stage 8.5 model, controller and workbench gates with bounded subprocesses."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from vel_env import ROOT, native_build, nonroot, tool_environment, work
from vel_gui_job import children, clean_children
from vel_jobs import install_cancel_handlers

APP = ROOT / "zephyr/apps/i2c_inspector"


def run_tests(directory, name, test, selections, env, timeout):
    log = directory / f"{name}.log"
    argv = [sys.executable, str(ROOT / test), *selections]
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as output:
        output.write(json.dumps(argv) + "\n")
        output.flush()
        process = subprocess.Popen(argv, env=env, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            rc = process.wait(timeout)
        except subprocess.TimeoutExpired:
            rc = 124
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(4)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(3)
            clean_children()
    text = log.read_text(errors="replace")
    counts = re.findall(r"^Ran (\d+) tests? in", text, re.MULTILINE)
    passed = rc == 0 and bool(counts) and "(skipped=" not in text
    return {"status": "PASS" if passed else "FAIL", "exit": rc,
            "tests": int(counts[-1]) if counts else 0,
            "log": log.name, "seconds": round(time.monotonic() - start, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("all", "host", "zephyr"), default="all")
    parser.add_argument("--gui", choices=("auto", "required", "skip"), default="auto")
    parser.add_argument("--output", type=Path, default=work("i2c-acceptance"))
    args = parser.parse_args()
    nonroot()
    install_cancel_handlers()
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Cannot enable owned process cleanup")
    args.output.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=args.output.resolve()))
    print(f"I2C evidence directory: {directory}", flush=True)
    env = tool_environment() | {"VEL_I2C_EVIDENCE": str(directory), "VEL_WORK_ROOT": str(directory / "work")}
    model = "tests/host/test_i2c.py"
    gui = "tests/gui/test_i2c_workbench.py"
    tests = {}
    if args.backend in ("host", "all"):
        tests["host"] = run_tests(directory, "host", model, ["Host"], env, 60)
        tests["headless"] = run_tests(directory, "headless", gui, ["Headless"], env, 28)
    if args.backend in ("all", "zephyr"):
        build = directory / "zephyr-build"
        try:
            with (directory / "zephyr-build.log").open("w", encoding="utf-8") as output:
                native_build(APP, build, log=output)
        except (OSError, subprocess.SubprocessError, SystemExit) as error:
            tests["zephyr"] = {"status": "FAIL", "log": "zephyr-build.log", "reason": str(error)}
        else:
            env["VEL_I2C_EXECUTABLE"] = str(build / "zephyr/zephyr.exe")
            tests["zephyr"] = run_tests(directory, "zephyr", model, ["Zephyr"], env, 85)
        finally:
            clean_children()
    if args.gui == "skip" or args.backend == "host":
        tests["wslg"] = {"status": "NOT RUN"}
    elif not env.get("DISPLAY"):
        tests["wslg"] = {"status": "BLOCKED", "reason": "DISPLAY is unset"}
    else:
        tests["wslg"] = run_tests(directory, "wslg", gui, ["Window"], env, 185)
    failed = any(item["status"] == "FAIL" for item in tests.values())
    blocked = any(item["status"] == "BLOCKED" for item in tests.values())
    if args.gui == "required" and tests["wslg"]["status"] != "PASS":
        failed = True
    result = {"status": "FAIL" if failed else "PARTIAL" if blocked else "PASS",
              "scope": "SIMULATED", "hardware": "NOT TESTED", "tests": tests,
              "tests_executed": sum(item.get("tests", 0) for item in tests.values()),
              "owned_children_after": children(os.getpid())}
    (directory / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(failed or bool(result["owned_children_after"]))


if __name__ == "__main__":
    sys.exit(main())
