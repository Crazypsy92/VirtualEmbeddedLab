"""CAN FrameTransport contract with lossless facades for existing backends."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CanMessage:
    identifier: int
    ide: bool
    rtr: bool
    dlc: int
    data: bytes
    timestamp_ns: int
    flags: int
    error_flags: int

    def __post_init__(self):
        limit = 0x1FFFFFFF if self.ide else 0x7FF
        if (type(self.ide) is not bool or type(self.rtr) is not bool or
                type(self.identifier) is not int or not 0 <= self.identifier <= limit or
                type(self.dlc) is not int or not 0 <= self.dlc <= 8 or
                not isinstance(self.data, bytes) or len(self.data) != (0 if self.rtr else self.dlc) or
                any(type(x) is not int or x < 0 for x in (self.timestamp_ns, self.flags, self.error_flags))):
            raise ValueError("Invalid Classical CAN frame")

    @classmethod
    def from_event(cls, row, timestamp_ns):
        """Normalize one actual API frame or IPC event without altering flags."""
        return cls(row["id"], row["ide"], row.get("rtr", False), row["dlc"],
                   bytes.fromhex(row["data"]), timestamp_ns, row["flags"],
                   row.get("error_flags", 0))

    def event(self):
        return {"id": self.identifier, "ide": self.ide, "rtr": self.rtr, "dlc": self.dlc,
                "data": self.data.hex(), "timestamp_ns": self.timestamp_ns, "flags": self.flags,
                "error_flags": self.error_flags}


class FrameTransport(ABC):
    """One read/write per CAN message; no bytes-as-frames assumption.

    Receiving returns None on timeout; disconnect raises ConnectionError.
    A backend must disclose unsupported frame properties and preserve actual
    timestamp provenance. A timed-out send has an unknown outcome.
    """
    @property
    @abstractmethod
    def metadata(self):
        pass

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def read_frame(self, *, timeout):
        pass

    @abstractmethod
    def write_frame(self, frame: CanMessage, *, timeout):
        pass


def loopback_frame(event, host_ns):
    """Zephyr API facade: H1 only produces Classical data frames."""
    return CanMessage.from_event(event, host_ns)


def model_frame(event, host_ns):
    """Host bus model facade: IPC frames are logical Classical data frames."""
    return CanMessage.from_event(event, host_ns)
