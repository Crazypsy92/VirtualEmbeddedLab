"""Host side of the native_sim RTU receive-ready control channel."""
import os
import select
import time

from pymodbus.client import ModbusSerialClient


def wait_rx_ready(control_fd, timeout=0.15, *, sequence=None):
    """Wait for one UART0 acknowledgement before sending the next RTU frame."""
    request = b"R" if sequence is None else b"T" + sequence.to_bytes(4, "big")
    if os.write(control_fd, request) != len(request):
        raise OSError("Could not request native_sim RTU receive-ready")
    if not select.select([control_fd], [], [], timeout)[0]:
        raise TimeoutError("native_sim RTU receive-ready acknowledgement timed out")
    acknowledgement = os.read(control_fd, 1)
    if acknowledgement != b"R":
        raise OSError(f"Unexpected native_sim RTU acknowledgement: {acknowledgement!r}")


class PtySerialClient(ModbusSerialClient):
    """Use elapsed time for the pymodbus PTY receive window."""

    def _wait_for_data(self):
        # Preserve pymodbus's data/size polling and timeout. WSL can step
        # CLOCK_REALTIME while this loop is waiting for the native UART.
        deadline = time.monotonic() + self.comm_params.timeout_connect
        size = 0
        while time.monotonic() <= deadline:
            available = self._in_waiting()
            if size and (not available or available == size):
                break
            if available:
                size = available
            time.sleep(self._recv_interval)
        return size
