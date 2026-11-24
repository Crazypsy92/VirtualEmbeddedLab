"""Validated Classical CAN requests and native_sim control-packet encoding."""
from dataclasses import dataclass
import re
import struct

FILTERS = {"all": 0, "standard": 1, "extended": 2}
IDE = 1


@dataclass(frozen=True)
class CanFrame:
    id: int
    extended: bool
    dlc: int
    data: bytes

    def __post_init__(self):
        if type(self.extended) is not bool:
            raise ValueError("选择 Standard 或 Extended")
        if type(self.id) is not int or not 0 <= self.id <= (0x1FFFFFFF if self.extended else 0x7FF):
            raise ValueError("CAN ID 超出所选帧格式的范围")
        if type(self.dlc) is not int or not 0 <= self.dlc <= 8:
            raise ValueError("Classical CAN 的 DLC 必须在 0–8")
        if not isinstance(self.data, bytes) or len(self.data) != self.dlc:
            raise ValueError("DATA 字节数必须等于 DLC")

    def fields(self):
        return {"id": self.id, "ide": self.extended, "flags": IDE if self.extended else 0,
                "dlc": self.dlc, "data": self.data.hex()}

    def packet(self, seq, mode):
        return struct.pack(">cIIBBB8s", b"C", seq, self.id, int(self.extended), self.dlc,
                           FILTERS[mode], self.data)


def parse_fields(format_, identifier, dlc, data):
    if format_ not in ("Standard", "Extended"):
        raise ValueError("选择 Standard 或 Extended")
    hexadecimal = identifier.strip()
    if re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]+", hexadecimal) is None:
        raise ValueError("CAN ID 请输入十六进制")
    tokens = data.split()
    if any(re.fullmatch(r"[0-9a-fA-F]{1,2}", token) is None for token in tokens):
        raise ValueError("DATA 使用以空格分隔的十六进制字节")
    if re.fullmatch(r"[0-9]+", dlc.strip()) is None:
        raise ValueError("DLC 请输入 0–8 的整数")
    payload = bytes(int(token, 16) for token in tokens)
    return CanFrame(int(hexadecimal, 16), format_ == "Extended", int(dlc), payload)


def parse_request(message):
    if not isinstance(message, dict) or set(message) != {"format", "id", "dlc", "data", "filter", "count"}:
        raise ValueError("无效 CAN 请求")
    if any(not isinstance(message[key], str) for key in ("format", "id", "dlc", "data", "filter")):
        raise ValueError("无效帧参数")
    count, mode = message["count"], message["filter"]
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("发送次数必须在 1–1000")
    if mode not in FILTERS:
        raise ValueError("无效接收过滤方式")
    return parse_fields(*(message[key] for key in ("format", "id", "dlc", "data"))), mode, count
