"""Bounded Host byte streams. Protocol framing belongs to the caller."""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, replace
import math
import os
import socket
import time


def seconds(value, *, zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (not zero and value == 0)):
        raise ValueError("Timeout must be finite and positive")
    return value


@dataclass(frozen=True)
class SerialConfig:
    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    read_timeout: float = .15
    write_timeout: float = .15
    inter_byte_timeout: float | None = None
    rs485_rts: bool = False

    def __post_init__(self):
        if not isinstance(self.port, str) or not self.port or len(self.port) > 1024 or "://" in self.port:
            raise ValueError("Use an explicit local serial device path or COM port")
        if type(self.baudrate) is not int or self.baudrate <= 0:
            raise ValueError("Invalid baud rate")
        if type(self.bytesize) is not int or self.bytesize not in (5, 6, 7, 8):
            raise ValueError("Invalid data bits")
        if self.parity not in ("N", "E", "O", "M", "S") or self.stopbits not in (1, 1.5, 2):
            raise ValueError("Invalid parity or stop bits")
        seconds(self.read_timeout)
        seconds(self.write_timeout)
        if self.inter_byte_timeout is not None:
            seconds(self.inter_byte_timeout)
        if type(self.rs485_rts) is not bool:
            raise ValueError("Invalid RS-485 RTS option")


@dataclass(frozen=True)
class TcpConfig:
    host: str
    port: int
    connect_timeout: float = 2
    read_timeout: float = 2
    write_timeout: float = 2

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip() or any(c.isspace() for c in self.host):
            raise ValueError("Invalid TCP host")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid TCP port")
        for limit in (self.connect_timeout, self.read_timeout, self.write_timeout):
            seconds(limit)


class ByteStreamTransport(ABC):
    """Read at most size bytes (empty on timeout); EOF raises ConnectionError.

    write() completes all bytes under one deadline or raises; failures may
    follow a partial write and callers must not blindly retry it. One owner
    serializes operations. close() is idempotent, including after an error.
    """
    backend = None

    def __init__(self, config, observer=None):
        self.config = config
        self.observer = observer
        self.correlation = None
        self._handle = None

    @property
    def connected(self):
        return self._handle is not None

    @property
    def is_open(self):
        return self.connected

    @property
    def metadata(self):
        return {"backend": self.backend, "configuration": asdict(self.config),
                "connected": self.connected}

    def _event(self, operation, data=b"", error=None):
        if self.observer is not None:
            self.observer({"operation": operation, "backend": self.backend,
                           "correlation": self.correlation, "monotonic_ns": time.monotonic_ns(),
                           "length": len(data), "hex": bytes(data).hex(),
                           "error": str(error) if error is not None else None})

    @abstractmethod
    def _connect(self):
        """Return a resource; clean up partial initialization on failure."""

    @abstractmethod
    def _receive(self, size, timeout):
        """Return at most size bytes, or empty bytes on timeout."""

    @abstractmethod
    def _send(self, data, timeout):
        """Attempt a write and return the accepted byte count."""

    def open(self):
        if not self.connected:
            try:
                self._handle = self._connect()
            except (OSError, ValueError) as error:
                self._event("open", error=error)
                raise
            self._event("open")
        return self

    def close(self):
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        try:
            handle.close()
        except OSError as error:
            self._event("close", error=error)
            raise
        self._event("close")

    def _require_open(self):
        if not self.connected:
            raise ConnectionError("Transport is closed")

    def _failed(self, operation, error):
        self._event(operation, error=error)
        try:
            self.close()
        except OSError:
            pass

    def read(self, size, *, timeout=None):
        if type(size) is not int or size < 0:
            raise ValueError("Read size must be a nonnegative integer")
        self._require_open()
        if size == 0:
            return b""
        limit = self.config.read_timeout if timeout is None else seconds(timeout, zero=True)
        try:
            data = self._receive(size, limit)
        except OSError as error:
            self._failed("read", error)
            raise
        self._event("read", data, error=None if data else "timeout")
        return data

    def write(self, data, *, timeout=None):
        self._require_open()
        deadline = time.monotonic() + (self.config.write_timeout if timeout is None else seconds(timeout))
        view = memoryview(data).cast("B")
        sent = 0
        try:
            while sent < len(view):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Write deadline reached after {sent} of {len(view)} bytes")
                count = self._send(view[sent:], remaining)
                if not 0 < count <= len(view) - sent:
                    raise ConnectionError("Transport made no valid write progress")
                self._event("write", view[sent:sent + count])
                sent += count
        except OSError as error:
            self._failed("write", error)
            raise
        return sent

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except OSError:
                pass


class SerialTransport(ByteStreamTransport):
    backend = "serial"

    def _connect(self):
        import serial
        from serial.rs485 import RS485Settings

        c = self.config
        handle = serial.Serial(port=c.port, baudrate=c.baudrate, bytesize=c.bytesize,
                               parity=c.parity, stopbits=c.stopbits, timeout=c.read_timeout,
                               write_timeout=c.write_timeout, inter_byte_timeout=c.inter_byte_timeout,
                               exclusive=True if os.name == "posix" else None)
        try:
            if c.rs485_rts:
                if not hasattr(handle, "rs485_mode"):
                    raise OSError("This serial driver does not support RS-485 direction control")
                handle.rs485_mode = RS485Settings()
        except BaseException:
            handle.close()
            raise
        return handle

    def _receive(self, size, timeout):
        if self._handle.timeout != timeout:
            self._handle.timeout = timeout
        return self._handle.read(size)

    def _send(self, data, timeout):
        self._handle.write_timeout = timeout
        return self._handle.write(data)

    @property
    def in_waiting(self):
        self._require_open()
        try:
            return self._handle.in_waiting
        except OSError as error:
            self._failed("read", error)
            raise

    def read_available(self, size, timeout):
        """Wait for one byte then drain only the bytes already queued."""
        if size <= 0:
            return super().read(size, timeout=timeout)
        first = super().read(1, timeout=timeout)
        if not first:
            return first
        return first + super().read(min(size - 1, self.in_waiting), timeout=0)

    def reset_input_buffer(self):
        self._require_open()
        try:
            self._handle.reset_input_buffer()
        except OSError as error:
            self._failed("discard", error)
            raise

    def fileno(self):
        self._require_open()
        return self._handle.fileno()


class PtyTransport(SerialTransport):
    backend = "pty"

    def __init__(self, config, observer=None, *, ready=None):
        super().__init__(config, observer)
        self.ready = ready

    def prepare(self, sequence):
        if self.ready is not None:
            self.ready(sequence)


class TcpTransport(ByteStreamTransport):
    backend = "tcp"

    def _connect(self):
        c = self.config
        return socket.create_connection((c.host, c.port), timeout=c.connect_timeout)

    def _receive(self, size, timeout):
        self._handle.settimeout(timeout)
        try:
            data = self._handle.recv(size)
        except (socket.timeout, BlockingIOError):
            return b""
        if not data:
            raise EOFError("TCP peer closed its write side")
        return data

    def read(self, size, *, timeout=None):
        try:
            return super().read(size, timeout=timeout)
        except EOFError as error:
            self._failed("eof", error)
            raise ConnectionError(str(error)) from error

    def _send(self, data, timeout):
        self._handle.settimeout(timeout)
        return self._handle.send(data)

    def recv(self, size):
        """Socket compatibility for the existing MBAP exact-read helper."""
        try:
            data = self.read(size)
        except ConnectionError as error:
            if isinstance(error.__cause__, EOFError):
                return b""
            raise
        if not data and size:
            raise TimeoutError("TCP read deadline reached")
        return data

    def sendall(self, data):
        self.write(data)

    def settimeout(self, timeout):
        self.config = replace(self.config, read_timeout=timeout, write_timeout=timeout)

    def shutdown(self, direction):
        self._require_open()
        self._handle.shutdown(direction)

    def setsockopt(self, *args):
        self._require_open()
        self._handle.setsockopt(*args)
