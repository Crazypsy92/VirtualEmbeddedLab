"""UART formatting and parsing verified native_sim RTU direction events."""
import re


BAUD = 115200
UART_LABELS = ("Start", *(f"D{i}" for i in range(8)), "Even", "Stop")
BIT_US = 1_000_000 / BAUD
CHAR_US = len(UART_LABELS) * BIT_US
DIRECTION_EVENT = re.compile(
    r"^RTU_EVENT id=(\d+) sim_ms=(\d+) event=(READY|RX_DISPATCH|RESPONSE_PREPARED|GPIO) de=([01]) re=([01])$"
)


def uart_bits(byte):
    if not 0 <= byte <= 255:
        raise ValueError("UART byte must be in 0–255")
    data = tuple((byte >> bit) & 1 for bit in range(8))
    return (0, *data, sum(data) % 2, 1)


def direction_event(line):
    match = DIRECTION_EVENT.fullmatch(line.strip())
    if match:
        sequence, elapsed, kind, de, re_enabled = match.groups()
        return {"sequence": int(sequence), "sim_ms": int(elapsed), "kind": kind,
                "de": int(de), "re": int(re_enabled)}
    return None


def host_events(record):
    device = "串口" if record.get("transport", {}).get("scope") == "SERIAL_DEVICE" else "PTY"
    return [(label, (record[key] - record["monotonic_ns"]) / 1e6)
            for key, label in (("tx_ns", f"Host TX · 写入{device}"),
                               ("rx_ns", f"Host RX · 读到最后一批{device}字节"),
                               ("finished_ns", "主站结束 · " + record["status"]))
            if record.get(key) is not None]
