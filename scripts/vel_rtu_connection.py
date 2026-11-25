"""RTU connection settings and simulator-only receive readiness binding."""
from dataclasses import dataclass, field
import json

from vel_transport import PtyTransport, SerialConfig, SerialTransport


@dataclass(frozen=True)
class RtuConnection:
    backend: str = "pty"
    simulation: bool = True
    port: str = ""
    settings: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.backend not in ("pty", "serial") or type(self.simulation) is not bool:
            raise ValueError("Backend must be pty or serial")
        if self.backend == "pty" and not self.simulation:
            raise ValueError("PTY backend requires a simulator endpoint")
        if type(self.settings) is not dict:
            raise ValueError("Invalid serial settings")
        self.serial_config(self.port if not self.simulation else self.port or "/dev/pts/simulator")

    def serial_config(self, endpoint):
        try:
            return SerialConfig(port=endpoint, **self.settings)
        except TypeError as error:
            raise ValueError("Unknown serial configuration field") from error

    @property
    def scope(self):
        if self.simulation:
            return "SERIAL_BACKEND_ON_PTY" if self.backend == "serial" else "PTY_SIMULATION"
        return "SERIAL_DEVICE"

    @classmethod
    def requested(cls, folder):
        path = folder / "transport-request.json"
        if not path.is_file():
            return cls(), False
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("Expected an RTU connection object")
        probe = record.pop("probe", False)
        if type(probe) is not bool:
            raise ValueError("Invalid connection probe flag")
        try:
            return cls(**record), probe
        except TypeError as error:
            raise ValueError("Unknown RTU connection field") from error

    def activate(self, endpoint, control_fd):
        from vel_modbus_transport import TransportSerialClient
        from pty_control import wait_rx_ready

        config = self.serial_config(endpoint)
        transport = (PtyTransport(config) if self.backend == "pty" else SerialTransport(config))
        readiness = None
        if control_fd is not None:
            def readiness(sequence):
                wait_rx_ready(control_fd, sequence=sequence)
        if isinstance(transport, PtyTransport):
            transport.ready = readiness
            readiness = transport.prepare
        return TransportSerialClient(transport), transport, readiness
