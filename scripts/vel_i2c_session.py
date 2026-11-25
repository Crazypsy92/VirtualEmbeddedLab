"""Bounded JSONL I2C worker for the workbench and acceptance runner."""
import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
import sys

from vel_env import ROOT, native_build
from vel_i2c import Bus, Request, integer
from vel_i2c_native import NativeController
from vel_jobs import install_cancel_handlers


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def command(bus, command):
    """Validate the entire request before changing the model or driving the controller."""
    if not isinstance(command, dict):
        raise ValueError("需要操作对象")
    op = command.get("op")
    if op == "scan" and set(command) == {"op", "khz"}:
        return bus.scan(command["khz"])
    if op == "wait" and set(command) == {"op", "us"}:
        bus.idle(command["us"])
        return []
    if op != "transfer" or set(command) - {"op", "request", "repeat", "gap_us"}:
        raise ValueError("未知 I2C 命令")
    count = integer(command.get("repeat", 1), 1, 100, "批量次数")
    gap = integer(command.get("gap_us", 0), 0, 25_000, "批量间隔 μs")
    request = Request(**command.get("request", {}))
    records = []
    for index in range(count):
        if index:
            bus.idle(gap)
        records.append(bus.transfer(request))
    return records


def session(folder, backend, executable=None):
    results = Counter()
    bus = None
    with ExitStack() as stack:
        if backend == "native":
            if executable is None:
                build = folder / "i2c-build"
                with (folder / "build.log").open("w") as log:
                    native_build(ROOT / "zephyr/apps/i2c_inspector", build, log=log)
                executable = build / "zephyr/zephyr.exe"
            native_log = stack.enter_context((folder / "i2c-native.log").open("w", encoding="utf-8"))
            adapter = stack.enter_context(NativeController(executable, native_log))
        else:
            adapter = None
        bus = Bus(adapter)
        stream = stack.enter_context((folder / "i2c-transactions.jsonl").open("w", encoding="utf-8"))
        emit("i2c_ready", **bus.metadata, native_pid=adapter.process.pid if adapter else None)
        try:
            while raw := sys.stdin.buffer.readline(4097):
                if len(raw) > 4096 or not raw.endswith(b"\n"):
                    raise ValueError("命令超过长度限制或缺少换行")
                try:
                    req = json.loads(raw)
                    rows = command(bus, req)
                except (ValueError, TypeError) as error:
                    emit("i2c_invalid", reason=str(error))
                    continue
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    results[row["status"]] += 1
                stream.flush()
                found = [f"0x{row['request']['address']:02X}" for row in rows if row["status"] == "OK"]
                report = {"count": len(rows), "time_ns": bus.time_ns, "status": counts(rows)}
                if req["op"] == "scan":
                    report["found"] = found
                elif rows:
                    report["last"] = {key: rows[-1][key] for key in ("status", "reason", "data", "sequence")}
                emit("i2c_result", **report)
        finally:
            (folder / "i2c-summary.json").write_text(json.dumps(bus.metadata | {
                "transactions": sum(results.values()), "status_counts": results, "time_ns": bus.time_ns,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counts(rows):
    return Counter(item["status"] for item in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("host", "native"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    install_cancel_handlers()
    try:
        session(args.folder, args.backend)
    except (OSError, RuntimeError, ValueError) as error:
        emit("i2c_error", reason=str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
