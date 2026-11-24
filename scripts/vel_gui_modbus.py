"""Independent interactive RTU master. JSON commands in, readback events out."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time
import tty

from vel_env import ROOT, native_build
from vel_jobs import install_cancel_handlers
from vel_rtu_session import RecordedMaster, SessionTransportError, run_protocol, validate_protocol

APP = ROOT / "zephyr/apps/modbus_rtu_slave"


def event(kind, **fields):
    print(json.dumps({"event": kind, "time": time.time(), **fields}), flush=True)


def validate(request):
    if not isinstance(request, dict):
        raise ValueError("Expected an operation object.")
    op = request.get("op")
    if op == "protocol":
        validate_protocol(request)
        return op
    if op == "read" and set(request) == {"op"}:
        return op
    if (op == "write" and set(request) == {"op", "index", "value"}
            and type(request["index"]) is int and 0 <= request["index"] < 8
            and type(request["value"]) is bool):
        return op
    if (op == "input" and set(request) == {"op", "mask"}
            and type(request["mask"]) is int and 0 <= request["mask"] < 16):
        return op
    raise ValueError("Unsupported or invalid GPIO operation.")


def wait_for_slave(process, path):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        log = path.read_text(errors="replace")
        if "MODBUS_INIT rc=0" in log:
            paths = re.findall(r"/dev/pts/\d+", log)
            if len(paths) >= 2:
                return paths[:2]
        if process.poll() is not None:
            raise RuntimeError(f"Slave exited with {process.returncode}: {path}")
        time.sleep(.05)
    raise TimeoutError(f"Slave startup timed out: {path}")


def commands(process):
    pending = b""
    while process.poll() is None:
        if not select.select([sys.stdin], [], [], .25)[0]:
            continue
        data = os.read(sys.stdin.fileno(), 4096)
        if not data:
            return
        pending += data
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield line
        if len(pending) > 4096:
            raise ValueError("Command exceeds input limit.")


def session(folder):
    # The interactive slave never shares an executable or a PTY with CLI acceptance.
    build = folder / "slave-build"
    with (folder / "build.log").open("w") as log:
        native_build(APP, build, log=log)
    slave_log = folder / "slave.log"
    argv = [build / "zephyr/zephyr.exe", "-rt", "-stop_at=115"]
    event("step", phase="slave", command=list(map(str, argv)))
    with (slave_log.open("w") as log, (folder / "rtu-wire.jsonl").open("w") as wire,
          (folder / "rtu-transactions.jsonl").open("w") as transactions):
        # The worker owns the slave shutdown. Separate its process group so the
        # supervisor's worker cancellation cannot deliver a second SIGTERM.
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        client = None
        control = None
        try:
            ctl, serial_port = wait_for_slave(process, slave_log)
            control = os.open(ctl, os.O_RDWR | os.O_NOCTTY)
            tty.setraw(control)

            client = RecordedMaster(serial_port, control, wire, transactions)
            call = client.call

            def readback():
                coils = call("read_coils", 0, count=8).bits[:8]
                inputs = call("read_discrete_inputs", 0, count=4).bits[:4]
                holding = call("read_holding_registers", 0, count=8).registers
                registers = call("read_input_registers", 0, count=8).registers
                do_mask = sum(1 << i for i, state in enumerate(coils) if state)
                if registers[7] != do_mask or holding[3] != do_mask:
                    raise RuntimeError("FC01 and the slave GPIO output bitmap disagree.")
                return dict(coils=coils, inputs=inputs, holding=holding, registers=registers)

            event("ready", **readback())
            for line in commands(process):
                try:
                    req = json.loads(line)
                    op = validate(req)
                    if op == "protocol":
                        outcome = run_protocol(req, call)
                        event("protocol_result", request=req, **outcome)
                        continue
                    if op == "write":
                        call("write_coil", req["index"], req["value"])
                    elif op == "input":
                        offset = slave_log.stat().st_size
                        os.write(control, bytes([65 + req["mask"]]))
                        until = time.monotonic() + 1
                        with slave_log.open() as monitor:
                            monitor.seek(offset)
                            expected = f"INPUT bits={req['mask']}"
                            while not any(line.strip() == expected for line in monitor):
                                if time.monotonic() >= until:
                                    raise RuntimeError("Slave did not acknowledge DI stimulus.")
                                time.sleep(.02)
                    data = readback()
                    if op == "write" and data["coils"][req["index"]] != req["value"]:
                        raise RuntimeError("FC01 readback did not confirm FC05.")
                    if op == "input" and data["registers"][6] != req["mask"]:
                        raise RuntimeError("FC02/IR6 did not confirm the input stimulus.")
                    event("result", request=req, **data)
                except SessionTransportError:
                    raise
                except (ValueError, OSError, RuntimeError) as error:
                    event("operation_error", reason=str(error))
        finally:
            if client:
                client.close()
            if control is not None:
                os.close(control)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(3)
            (folder / "slave-exit.json").write_text(json.dumps({"pid": process.pid, "exit": process.returncode}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    install_cancel_handlers()
    try:
        session(args.folder)
    except Exception as error:
        event("session_error", reason=str(error))
        sys.exit(1)
