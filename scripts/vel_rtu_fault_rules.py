"""One-shot Modbus RTU fault presets and their byte transformations."""
from dataclasses import dataclass
import struct

from vel_rtu_frames import crc16


@dataclass(frozen=True)
class Rule:
    label: str
    direction: str
    status: str
    exception: int | None = None


RULES = {
    "tx_crc": Rule("请求 CRC 损坏", "tx", "TIMEOUT"),
    "tx_truncate": Rule("请求截断", "tx", "TIMEOUT"),
    "tx_drop": Rule("请求丢弃", "tx", "TIMEOUT"),
    "tx_unit": Rule("错误从站地址", "tx", "TIMEOUT"),
    "tx_function": Rule("未知功能码", "tx", "EXCEPTION", 1),
    "tx_address": Rule("非法数据地址", "tx", "EXCEPTION", 2),
    "tx_value": Rule("非法数据值", "tx", "EXCEPTION", 3),
    "rx_crc": Rule("响应 CRC 损坏", "rx", "CRC_ERROR"),
    "rx_drop": Rule("响应丢弃", "rx", "TIMEOUT"),
    "rx_delay": Rule("响应延迟 220 ms", "rx", "LATE_RESPONSE"),
}
TIMEOUT = .15
DELAY = .22


def adu(body):
    return body + crc16(body).to_bytes(2, "little")


def original_request(name, holding):
    if name.startswith("rx_"):
        return adu(struct.pack(">BBHH", 1, 3, 0, 1))
    # Rejected writes must leave a detectable state unchanged. HR3 drives DO.
    address = 0 if name == "tx_value" else 3
    value = (holding[0] + 1) % 3 if address == 0 else holding[3] ^ 1
    return adu(struct.pack(">BBHH", 1, 6, address, value))


def request_bytes(name, original):
    if name == "tx_crc":
        return original[:-1] + bytes((original[-1] ^ 1,))
    if name == "tx_truncate":
        return original[:3]
    if name == "tx_drop":
        return b""
    if name == "tx_unit":
        return adu(b"\x02" + original[1:-2])
    if name == "tx_function":
        return adu(original[:1] + b"\x41" + original[2:-2])
    if name == "tx_address":
        return adu(original[:2] + b"\x00\x08" + original[4:-2])
    if name == "tx_value":
        return adu(original[:4] + b"\x00\x03")
    return original


def response_bytes(name, incoming):
    if name in ("rx_drop", "rx_delay"):
        return b""
    if name == "rx_crc" and incoming:
        return incoming[:-1] + bytes((incoming[-1] ^ 1,))
    return incoming


def changes(before, after):
    return [{"offset": index,
             "before": f"{before[index]:02X}" if index < len(before) else None,
             "after": f"{after[index]:02X}" if index < len(after) else None}
            for index in range(max(len(before), len(after)))
            if before[index:index + 1] != after[index:index + 1]]
