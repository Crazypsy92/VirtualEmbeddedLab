#!/usr/bin/env python3
"""Audit Stage 8.2 protocol logs against actual native_sim PTY traffic."""
import argparse
import json
from pathlib import Path
import re

from diagnose_stage8_2 import crc, expected, frame

SETUP_REQUESTS = 19
STRESS_REQUESTS = 1000
TOTAL_REQUESTS = 1026


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(report_path, trace_path):
    report = json.loads(report_path.read_text())
    host = json.loads(Path(report["transcript"]).read_text())
    paths = re.findall(r"/dev/pts/(\d+)", Path(report["log"]).read_text())
    require(len(paths) >= 2, "Missing RTU PTY from slave startup")
    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    slave = [event for event in events if event["pty"] == int(paths[1])]
    require(report["status"] == "PASS" and report["successful_transactions"] == TOTAL_REQUESTS,
            "Incomplete original protocol suite")
    require(report["process_exit"] == 0, "Slave did not shut down cleanly")
    stats = report["stats"]
    require(all(stats[k] == TOTAL_REQUESTS for k in ("requests", "valid", "responses")),
            "Slave request and prepared-response totals differ from the host")
    require(all(stats[k] == 0 for k in ("errors", "exceptions", "crc")),
            "Unexpected slave errors in normal protocol run")
    require(len(host) == 2 * TOTAL_REQUESTS, "Missing or extra host frame")
    previous_response = None
    interval_ns = []
    elapsed_ns = []
    slave_rxs = bytearray()
    transaction = 0
    for event in slave:
        chunk = bytes.fromhex(event["hex"])
        require(len(chunk) == event["bytes"], "Incomplete native PTY event")
        if event["dir"] == "rx":
            slave_rxs.extend(chunk)
            continue
        require(event["dir"] == "tx" and transaction < TOTAL_REQUESTS,
                "Unknown native PTY event or extra response")
        number = transaction + 1
        tx, rx = host[2 * transaction:2 * transaction + 2]
        request, response = (bytes.fromhex(row["hex"]) for row in (tx, rx))
        require(tx["direction"] == "request" and rx["direction"] == "response",
                f"Wrong host event order at transaction {number}")
        require(slave_rxs == request and chunk == response,
                f"Native PTY bytes differ at transaction {number}")
        require(len(request) >= 5 and len(response) >= 5 and
                all(crc(data[:-2]) == data[-2:] for data in (request, response)),
                f"Invalid host frame CRC at transaction {number}")
        require(request[:2] == response[:2],
                f"Slave ID or function mismatch at transaction {number}")
        sent = round(tx["time"] * 1e9)
        received = round(rx["time"] * 1e9)
        require(sent <= event["ns"] <= received,
                f"Slave emitted a response outside the host frame window at {number}")
        if SETUP_REQUESTS <= transaction < SETUP_REQUESTS + STRESS_REQUESTS:
            stress = transaction - SETUP_REQUESTS
            level, index = divmod(stress, 4)
            coil = level % 8
            cases = [(6, 3, level), (4, 7, 1), (5, coil, 0xFF00), (1, coil, 1)]
            expected_request = frame(*cases[index])
            require(request == expected_request and response == expected(expected_request, level, True),
                    f"Unexpected stress payload at transaction {number}")
            require(0 <= received - sent <= 150_000_000, f"Late response at {number}")
            elapsed_ns.append(received - sent)
            interval_ns.append(sent - previous_response)
        previous_response = received
        slave_rxs.clear()
        transaction += 1
    require(transaction == TOTAL_REQUESTS and not slave_rxs and len(elapsed_ns) == STRESS_REQUESTS,
            "Missing response or extra request bytes on native PTY")
    return {"status": "PASS", "all_request_response_pairs": transaction,
            "stress_request_response_pairs": len(elapsed_ns), "wire_mismatches": 0,
            "retries": 0, "rtu_timeout_seconds": .15, "stats": stats,
            "response_elapsed_ns": distribution(elapsed_ns),
            "previous_rx_to_tx_ns": distribution(interval_ns),
            "slave_process_exit": report["process_exit"]}


def distribution(values):
    ordered = sorted(values)
    return {"min": ordered[0], "median": ordered[len(ordered) // 2], "max": ordered[-1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("slave_pty_trace", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.acceptance, args.slave_pty_trace), indent=2))
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f"Wire audit failed: {error}\n")


if __name__ == "__main__":
    main()
