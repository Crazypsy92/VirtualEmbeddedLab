#!/usr/bin/env python3
"""Measure host serial, native PTY syscalls and Zephyr state without retrying."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import time
import tty

from vel_env import ROOT, ZEPHYR_REV, tool_environment, zephyr_base
from vel_jobs import install_cancel_handlers


def crc(payload):
    value = 0xFFFF
    for byte in payload:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value.to_bytes(2, "little")


def frame(fc, address, value):
    pdu = struct.pack(">BBHH", 1, fc, address, value)
    return pdu + crc(pdu)


def expected(tx, level, coil):
    fc = tx[1]
    if fc in (5, 6):
        return tx
    pdu = bytes((1, fc, 1, int(coil))) if fc == 1 else bytes((1, fc, 2, 0, level))
    return pdu + crc(pdu)


def classify(data, wanted):
    if not data:
        return "empty"
    length = 5 if len(data) > 1 and data[1] & 128 else len(wanted)
    if len(data) < length:
        return "partial"
    if crc(data[:length-2]) != data[length-2:length]:
        return "crc"
    if len(data) > length:
        return "duplicate" if data == wanted * 2 else "trailing"
    if data == wanted:
        return "ok"
    return "exception" if data[1] & 128 else "mismatch"


def wait_slave(proc, path):
    until = time.monotonic() + 9
    while time.monotonic() < until and proc.poll() is None:
        text = path.read_text(errors="replace")
        paths = re.findall(r"/dev/pts/\d+", text)
        if "MODBUS_INIT rc=0" in text and len(paths) >= 2:
            return paths[:2]
        time.sleep(.01)
    raise RuntimeError(f"Slave startup failed: {path}")


def raw_exchange(port, wire, length, timeout):
    port.write(wire)
    response = bytearray()
    deadline = time.monotonic() + timeout
    while len(response) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([port.fileno()], [], [], remaining)[0]:
            break
        response.extend(port.read(length - len(response)))
        if len(response) >= 2 and response[1] & 128:
            length = 5
    if port.in_waiting:
        response.extend(port.read(port.in_waiting))
    return bytes(response)


def main():
    from pathlib import Path
    import serial
    from pymodbus.client import ModbusSerialClient
    import pymodbus.client.serial as serial_client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=lambda s: Path(s).resolve())
    parser.add_argument("output", type=lambda s: Path(s).resolve())
    parser.add_argument("--transport", choices=["pymodbus", "raw"], default="pymodbus")
    parser.add_argument("--timeout", type=float, default=.15)
    parser.add_argument("--gap-ms", type=float, default=0)
    parser.add_argument("--cycles", type=int, default=250)
    parser.add_argument("--ready", action="store_true", help="use native_sim receive-ready control")
    parser.add_argument("--monotonic", action="store_true", help="use the PTY client elapsed-time receive window")
    parser.add_argument("--no-trace", action="store_true")
    args = parser.parse_args()
    if not (0 < args.timeout <= 2 and 0 <= args.gap_ms <= 100 and 1 <= args.cycles <= 500):
        parser.error("Invalid diagnostic bounds")
    if args.monotonic and args.transport != "pymodbus":
        parser.error("--monotonic requires --transport pymodbus")
    if args.ready or args.monotonic:
        sys.path.insert(0, str(ROOT / "host/modbus_master"))
        from pty_control import PtySerialClient, wait_rx_ready

    folder = args.output
    folder.mkdir(parents=True, exist_ok=False)
    metadata = dict(status="FAIL", source_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        zephyr_build_sha=ZEPHYR_REV, receive_ready=args.ready, monotonic_receive=args.monotonic,
        zephyr=str(zephyr_base()), timeout_seconds=args.timeout, retries=0,
        gap_ms=args.gap_ms, transport=args.transport, cycles=args.cycles,
        pymodbus=version("pymodbus"), pyserial=version("pyserial"),
        argv=sys.argv, elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        parity="N (PTY only)", baudrate=115200, hardware="NOT TESTED",
        trace_enabled=not args.no_trace)
    install_cancel_handlers()
    env = tool_environment()
    process = client = port = control = None
    rows = []
    clock_reads = []

    class ClockProbe:
        def time(self):
            wall = time.time()
            clock_reads.append((time.monotonic_ns(), round(wall * 1_000_000_000)))
            return wall

        def __getattr__(self, name):
            return getattr(time, name)

    if args.transport == "pymodbus":
        serial_client.time = ClockProbe()
    serial_events = []
    late = b""
    slave_log = folder / "slave.log"
    with slave_log.open("w") as output, (folder / "wire.jsonl").open("w") as trace:
        try:
            if not args.no_trace:
                library = folder / "trace_pty.so"
                subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                                ROOT / "host/modbus_master/trace_pty.c", "-o", library, "-ldl"],
                               check=True, timeout=25)
                env.update(LD_PRELOAD=str(library), VEL_PTY_TRACE=str(folder / "slave-pty.jsonl"))
            cmd = [args.elf, "-rt", "-stop_at=110"]
            metadata["slave_command"] = list(map(str, cmd))
            process = subprocess.Popen(cmd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            control_path, data_path = wait_slave(process, slave_log)
            metadata["pty"] = int(data_path.rsplit("/", 1)[1])
            control = os.open(control_path, os.O_RDWR | os.O_NOCTTY)
            tty.setraw(control)
            if args.transport == "pymodbus":
                client_type = PtySerialClient if args.monotonic else ModbusSerialClient
                client = client_type(data_path, baudrate=115200, parity="N",
                                            timeout=args.timeout, retries=0)
                if not client.connect():
                    raise RuntimeError("Cannot open slave PTY")
                port = client.socket
            else:
                port = serial.Serial(data_path, 115200, parity="N", timeout=0,
                                     write_timeout=args.timeout)
            original_read, original_write = port.read, port.write

            def serial_io(op, function, arg):
                start = time.monotonic_ns()
                result = function(arg)
                data = result if op == "rx" else arg[:result]
                serial_events.append(dict(op=op, started_ns=start, ns=time.monotonic_ns(),
                                          bytes=len(data), hex=data.hex()))
                return result

            port.read = lambda n: serial_io("rx", original_read, n)
            port.write = lambda data: serial_io("tx", original_write, data)
            previous_end = None
            writes = 0
            for i in range(args.cycles):
                level, index = i & 255, i % 8
                cases = [(6, 3, level), (4, 7, 1), (5, index, 0xFF00), (1, index, 1)]
                for fc, address, value in cases:
                    if args.gap_ms:
                        time.sleep(args.gap_ms / 1000)
                    tx = frame(fc, address, value)
                    wanted = expected(tx, level, True)
                    sequence = len(rows) + 1
                    serial_events.clear()
                    clock_reads.clear()
                    exception = None
                    started = time.monotonic_ns()
                    try:
                        if args.ready:
                            wait_rx_ready(control)
                        if client is None:
                            raw_exchange(port, tx, len(wanted), args.timeout)
                        elif fc == 6:
                            client.write_register(address, value, device_id=1)
                        elif fc == 4:
                            client.read_input_registers(address, count=value, device_id=1)
                        elif fc == 5:
                            client.write_coil(address, True, device_id=1)
                        else:
                            client.read_coils(address, count=value, device_id=1)
                    except Exception as error:
                        exception = f"{type(error).__name__}: {error}"
                    ended = time.monotonic_ns()
                    observed = b"".join(bytes.fromhex(v["hex"]) for v in serial_events if v["op"] == "rx")
                    sent = b"".join(bytes.fromhex(v["hex"]) for v in serial_events if v["op"] == "tx")
                    status = classify(observed, wanted)
                    if not sent and exception:
                        status = "pre_tx_error"
                    elif sent != tx:
                        status = "tx_mismatch"
                    elif status == "ok" and exception:
                        status = "host_parse_error"
                    row = dict(sequence=sequence, started_ns=started, finished_ns=ended,
                               gap_ns=started-previous_end if previous_end else None,
                               fc=fc, address=address, value=value, expected_hex=wanted.hex(),
                               expected_length=len(wanted), pdu=tx[1:-2].hex(), tx=sent.hex(),
                               tx_crc_ok=len(sent) >= 5 and crc(sent[:-2]) == sent[-2:],
                               rx=observed.hex(), rx_bytes=len(observed),
                               rx_crc_ok=len(observed) >= 5 and crc(observed[:-2]) == observed[-2:],
                               classification=status, error=exception, serial=serial_events.copy(),
                               clock_reads=clock_reads.copy() if status != "ok" else [],
                               clock_offset_span_ns=(max(offsets)-min(offsets)) if
                               (offsets := [wall-mono for mono, wall in clock_reads]) else None)
                    previous_end = ended
                    rows.append(row)
                    trace.write(json.dumps(row) + "\n")
                    if status != "ok":
                        trace.flush()
                        os.write(control, b"S")
                        until = time.monotonic() + .35
                        while time.monotonic() < until:
                            if select.select([port.fileno()], [], [], .02)[0]:
                                late += os.read(port.fileno(), 256)
                        metadata["late_rx_hex"] = late.hex()
                        if late:
                            metadata["late_classification"] = classify(observed + late, wanted)
                        break
                    if fc in (5, 6):
                        writes += 1
                if rows[-1]["classification"] != "ok":
                    break
            metadata["expected_writes"] = writes
            metadata["status"] = "PASS" if len(rows) == args.cycles * 4 and all(
                row["classification"] == "ok" for row in rows) else "FAIL"
        except Exception as error:
            metadata["error"] = f"{type(error).__name__}: {error}"
        finally:
            if control is not None:
                try:
                    os.write(control, b"S")
                    time.sleep(.04)
                except OSError as error:
                    metadata["stats_error"] = str(error)
                finally:
                    os.close(control)
            if client:
                client.close()
            elif port:
                port.close()
            if process is not None:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(3)
                metadata["slave_exit"] = process.returncode
            text = slave_log.read_text(errors="replace")
            metadata["last_stats"] = [line for line in text.splitlines() if line.startswith(("STATS ", "THREAD "))][-8:]
            metadata["transactions"] = len(rows)
            metadata["successful"] = sum(row["classification"] == "ok" for row in rows)
            metadata["window"] = rows[-11:]
            metadata["exit_code"] = int(metadata["status"] != "PASS")
            (folder / "result.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(folder, metadata["status"], metadata["successful"], "/", len(rows), flush=True)
    return metadata["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
