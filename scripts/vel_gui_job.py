"""Linux supervisor for one GUI job, including legacy nested process groups."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from vel_env import ROOT, tool_environment, work
from vel_gui_features import BY_ID, capabilities, dependencies_for, invocation, requires_simulation
from vel_jobs import BusyWorkspace, workspace_lock

EVIDENCE = ("VEL_STAGE1_EVIDENCE", "VEL_STAGE3_EVIDENCE", "VEL_STAGE4_EVIDENCE",
            "VEL_STAGE5_EVIDENCE", "VEL_STAGE8_1_EVIDENCE", "VEL_STAGE8_2_EVIDENCE",
            "VEL_STAGE8_3_EVIDENCE", "VEL_STAGE8_3_1_EVIDENCE")


def children(pid):
    try:
        return [int(item) for item in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except (FileNotFoundError, ProcessLookupError):
        return []


def send(pid, sig):
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        signal.pidfd_send_signal(descriptor, sig)
    except ProcessLookupError:
        pass
    finally:
        os.close(descriptor)


def clean_children():
    # Orphans from helpers using start_new_session reparent to this subreaper.
    deadline = time.monotonic() + 6
    while owned := children(os.getpid()):
        sig = signal.SIGTERM if time.monotonic() < deadline - 3 else signal.SIGKILL
        for pid in owned:
            send(pid, sig)
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned process cleanup exceeded deadline")
        time.sleep(.05)


def run(args, resolve=invocation):
    result = {"id": args.feature, "mode": args.mode, "started": time.time(), "status": "FAIL"}
    cancelled = False
    def request_stop(*_):
        nonlocal cancelled
        cancelled = True

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGTSTP):
        signal.signal(sig, request_stop)
    try:
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "Cannot enable owned process cleanup")
        simulation = requires_simulation(args.folder) if args.feature == "rtu" else True
        argv = resolve(args.feature, args.mode, args.folder,
                       capabilities(dependencies_for(BY_ID[args.feature], args.mode, simulation)))
        result["command"] = argv
        env = tool_environment()
        env["PYTHONUNBUFFERED"] = "1"
        # Legacy shared work directories become private to this job.
        env["VEL_WORK_ROOT"] = str(args.folder / "work")
        for key in EVIDENCE:
            env[key] = str(args.folder / key[4:].lower())
        if args.feature == "gpio":
            env["VEL_GUI_RENODE_CACHE"] = str(work("simulation_stage8_1_ws") / "renode-1.17.0.tar.gz")
        lockdir = work("gui-h1/locks")
        lockdir.mkdir(parents=True, exist_ok=True)
        resource = {"arm": "arm", "zephyr": "zephyr", "fatfs": "host"}.get(args.feature, args.feature)
        with workspace_lock(lockdir / (resource + ".lock")):
            if cancelled:
                result.update(status="CANCELLED", exit=130)
                return 130
            proc = subprocess.Popen(argv, cwd=ROOT, env=env, start_new_session=True)
            result["pid"] = proc.pid
            deadline = time.monotonic() + args.timeout
            try:
                while proc.poll() is None and not cancelled and time.monotonic() < deadline:
                    time.sleep(.08)
                if proc.poll() is None:
                    timed_out = not cancelled
                    result.update(status="TIMEOUT" if timed_out else "CANCELLED",
                                  exit=124 if timed_out else 130)
                elif cancelled:
                    result.update(status="CANCELLED", exit=130)
                else:
                    outcome = "COMPLETED" if args.feature == "i2c" or args.mode in ("交互会话", "多节点总线") else "PASS"
                    result.update(status=outcome if proc.returncode == 0 else "FAIL", exit=proc.returncode)
            finally:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(4)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        proc.wait(3)
                clean_children()
                result["child_exit"] = proc.returncode
        return result["exit"]
    except (ValueError, BusyWorkspace, OSError, RuntimeError) as error:
        result.update(status="UNAVAILABLE" if isinstance(error, ValueError) else
                      "BUSY" if isinstance(error, BusyWorkspace) else "FAIL",
                      exit=75 if isinstance(error, BusyWorkspace) else 2, reason=str(error))
        print(str(error), flush=True)
        return result["exit"]
    finally:
        transport = args.folder / "transport.json"
        if args.feature == "rtu" and transport.is_file():
            result["transport"] = json.loads(transport.read_text(encoding="utf-8"))
        result["finished"] = time.time()
        (args.folder / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("feature", choices=BY_ID)
    parser.add_argument("mode")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--timeout", type=float, choices=range(1, 901), default=480)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
