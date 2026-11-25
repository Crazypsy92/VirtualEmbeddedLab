"""Summarize actual gateway audit records and zero-retry worker traces."""
from collections import Counter, defaultdict, deque
import json
from pathlib import Path
import re

from vel_rtu_frames import crc16

FUNCTIONS = {1, 2, 3, 4, 5, 6, 15, 16}


def timings(values):
    ordered = sorted(values)
    assert ordered
    return {label: round(1000 * ordered[round((len(ordered) - 1) * pct)], 3)
            for label, pct in (("min", 0), ("p50", .5), ("p95", .95), ("p99", .99), ("max", 1))}


def fields(line):
    return {key: int(value) for key, value in re.findall(r"(\w+)=(-?\d+)", line)}


def relay_frames(events, direction):
    """Reassemble the actual relay byte stream independently of read chunk boundaries."""
    data = b"".join(bytes.fromhex(event["hex"]) for event in events
                    if event["direction"] == direction)
    offset = 0
    frames = []
    while offset < len(data):
        assert len(data) - offset >= 5
        fc = data[offset + 1]
        assert fc in FUNCTIONS
        if direction == 0 and fc <= 4:
            length = 5 + data[offset + 2]
        elif direction == 1 and fc in (15, 16):
            assert len(data) - offset >= 9
            length = 9 + data[offset + 6]
        else:
            length = 8
        raw = data[offset:offset + length]
        assert len(raw) == length and crc16(raw[:-2]) == int.from_bytes(raw[-2:], "little"), raw.hex()
        frames.append(raw[:-2])
        offset += length
    return frames


def audit_workers(results, gateway_log, relay, mode):
    parsed = defaultdict(list)
    for line in Path(gateway_log).read_text().splitlines():
        key = line.split(" ", 1)[0]
        if key in ("TCP_RECEIVED", "RTU", "TCP_SENT", "GW_STATS"):
            parsed[key].append(fields(line))
    counter_keys = ("tid", "slot")
    stages = [Counter(tuple(row[k] for k in counter_keys) for row in parsed[stage])
              for stage in ("TCP_RECEIVED", "RTU", "TCP_SENT")]
    generations = [Counter((row["tid"], row["slot"], row["generation"]) for row in parsed[stage])
                   for stage in ("TCP_RECEIVED", "RTU")]
    assert stages[0] == stages[1] == stages[2], "lost or duplicate gateway stages"
    assert generations[0] == generations[1], "gateway changed client generation"
    assert all(row["rc"] == 0 and row["issued"] == 1 for row in parsed["RTU"])
    stats = parsed["GW_STATS"]
    peak_active = max(x["max_active"] for x in stats)
    assert peak_active == 1
    assert all(not row["timeouts"] and not row["exceptions"] and not row["rejected"] and not row["stale"]
               for row in stats)
    counts = Counter()
    latencies = []
    starts, ends = [], []
    observed_tids = Counter()
    client_summary = []
    by_tid = defaultdict(deque)
    for client in results:
        rows = [json.loads(line) for path in client["wires"] for line in Path(path).read_text().splitlines()]
        assert len(rows) == client["transactions"] + (0 if mode == "tid" else 1)
        own = Counter()
        for row in rows:
            assert row["request_tid"] == row["response_tid"] and row["request_unit"] == row["unit"] == 1
            assert row["request_fc"] == row["response_fc"]
            own[row["request_fc"]] += 1
            observed_tids[row["request_tid"]] += 1
            by_tid[row["request_tid"]].append(row)
        values = [v["end"] - v["start"] for v in rows]
        starts.append(rows[0]["start"])
        ends.append(rows[-1]["end"])
        counts.update(own)
        latencies.extend(values)
        client_summary.append({"transactions": len(rows), "functions": dict(own), "latency_ms": timings(values)})
    gateway_tids = Counter(row["tid"] for row in parsed["RTU"])
    assert all(gateway_tids[tid] == count for tid, count in observed_tids.items())
    assert relay.error is None
    requests = relay_frames(relay.events, 1)
    responses = relay_frames(relay.events, 0)
    assert len(requests) == len(responses) == len(parsed["RTU"])
    for stage, request, response in zip(parsed["RTU"], requests, responses):
        tid = stage["tid"]
        if tid not in observed_tids:
            continue
        host = by_tid[tid].popleft()
        assert request == bytes.fromhex(host["request"])[6:], (tid, request.hex())
        assert response == bytes((host["unit"],)) + bytes.fromhex(host["pdu"]), (tid, response.hex())
    assert all(not queue for queue in by_tid.values())
    if mode != "tid":
        assert set(counts) == FUNCTIONS
    return {"functions": dict(counts), "actual_worker_requests": len(latencies),
            "crc_checked_relay_pairs": len(requests),
            "throughput_per_second": round(len(latencies) / (max(ends) - min(starts)), 3),
            "wall_active_seconds": max(ends) - min(starts), "latency_ms": timings(latencies),
            "client_metrics": client_summary, "rtu_max_active": peak_active,
            "request_queue_observed_peak": max(row["queued"] for row in parsed["TCP_RECEIVED"]),
            "timeouts": stats[-1]["timeouts"], "exceptions": stats[-1]["exceptions"],
            "stale": stats[-1]["stale"], "rejected": stats[-1]["rejected"]}


def resource_trend(samples):
    keys = ("fds", "Threads", "VmRSS", "VmHWM", "VmSize")
    def number(row, key):
        return int(str(row[key]).split()[0])
    return {key: dict(first=number(samples[0], key), last=number(samples[-1], key),
                      peak=max(number(row, key) for row in samples),
                      settled_min=min(number(row, key) for row in samples[5:-1]),
                      settled_max=max(number(row, key) for row in samples[5:-1]))
            for key in keys}
