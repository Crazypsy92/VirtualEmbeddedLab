"""Bind existing pymodbus framing and transactions to bounded Host transports."""
from pathlib import Path
import sys
import time

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

from vel_transport import TcpTransport

HOST_MASTER = Path(__file__).resolve().parents[1] / "host/modbus_master"
sys.path.insert(0, str(HOST_MASTER))
from pty_control import PtySerialClient


class TransportSerialClient(PtySerialClient):
    """Keep the existing monotonic RTU framer/receive behavior."""
    def __init__(self, channel, **kwargs):
        self.channel = channel
        c = channel.config
        super().__init__(c.port, baudrate=c.baudrate, bytesize=c.bytesize,
                         parity=c.parity, stopbits=c.stopbits, timeout=c.read_timeout, retries=0, **kwargs)

    def connect(self):
        if not self.channel.connected:
            self.channel.open()
            self.last_frame_end = None
        self.socket = self.channel
        return True

    def _in_waiting(self):
        return self.channel.in_waiting


class TransportTcpClient(ModbusTcpClient):
    """The Modbus TCP parser lives in pymodbus. recv returns a stream chunk."""
    def __init__(self, channel: TcpTransport, **kwargs):
        self.channel = channel
        c = channel.config
        super().__init__(c.host, port=c.port, timeout=c.read_timeout, retries=0, **kwargs)

    def connect(self):
        self.channel.open()
        self.socket = self.channel
        return True

    def send(self, request, addr=None):
        return self.channel.write(request) if request else 0

    def recv(self, size):
        try:
            data = self.channel.read(4096 if size is None else size)
        except ConnectionError as error:
            self.close()
            raise ConnectionException(str(error)) from error
        self.last_frame_end = round(time.monotonic(), 6)
        return data
