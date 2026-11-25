"""Transport-only acceptance with real PTY pairs and localhost TCP sockets."""
from collections import deque
from contextlib import closing
import json
import os
from pathlib import Path
import pty
import socket
import struct
import sys
import threading
import time
import tty
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from vel_frame_transport import CanMessage, FrameTransport, loopback_frame, model_frame
from vel_transport import ByteStreamTransport, PtyTransport, SerialConfig, SerialTransport, TcpConfig, TcpTransport


def read_exact(read, size):
    data = bytearray()
    while len(data) < size:
        part = read(size - len(data))
        if not part:
            raise TimeoutError("incomplete test message")
        data.extend(part)
    return bytes(data)


def sample(case, **fields):
    if path := os.environ.get("VEL_TRANSPORT_TEST_RECORDS"):
        with Path(path).open("a", encoding="utf-8") as file:
            file.write(json.dumps({"case": case, **fields}) + "\n")


class Contract(unittest.TestCase):
    def test_short_writes_and_exceptional_close(self):
        class Short(ByteStreamTransport):
            def _connect(self):
                return self

            def close(self):
                super().close()

            def _receive(self, size, timeout):
                return b"x"[:size]

            def _send(self, data, timeout):
                return min(len(data), 2)
        log = []
        from unittest.mock import Mock
        channel = Short(SerialConfig("/unused"), log.append)
        handle = Mock()
        handle.close.side_effect = OSError("injected close")
        channel._connect = lambda: handle
        channel.open()
        channel.open()
        channel.correlation = 7
        self.assertEqual(channel.read(9), b"x")
        self.assertEqual(channel.write(b"12345"), 5)
        self.assertEqual([e["hex"] for e in log if e["operation"] == "write"], ["3132", "3334", "35"])
        self.assertTrue(all(e["correlation"] == 7 for e in log if e["operation"] in ("write", "read")))
        with self.assertRaisesRegex(OSError, "injected close"):
            channel.close()
        self.assertFalse(channel.connected)
        channel.close()
        handle.close.assert_called_once()

    def test_context_preserves_original_exception_and_bounded_write(self):
        from unittest.mock import Mock
        class Stalled(ByteStreamTransport):
            def _connect(self):
                return handle

            def _receive(self, size, timeout):
                return b""

            def _send(self, data, timeout):
                self.elapsed = timeout
                raise TimeoutError("short write deadline")
        handle = Mock()
        handle.close.side_effect = OSError("close error")
        channel = Stalled(SerialConfig("/unused"))
        with self.assertRaisesRegex(TimeoutError, "short write deadline"):
            with channel:
                channel.write(b"12")
        self.assertFalse(channel.connected)
        self.assertLessEqual(channel.elapsed, .15)

    def test_frame_contract(self):
        class QueueTransport(FrameTransport):
            def __init__(self):
                self.queue = deque()
                self.connected = False

            @property
            def metadata(self):
                return {"backend": "contract fixture", "connected": self.connected}

            def open(self):
                self.connected = True

            def close(self):
                self.connected = False

            def read_frame(self, *, timeout):
                if not self.connected:
                    raise ConnectionError
                return self.queue.popleft() if self.queue else None

            def write_frame(self, frame, *, timeout):
                if not self.connected:
                    raise ConnectionError
                self.queue.append(frame)
        frame = CanMessage(0x1FFFFFFF, True, False, 8, b"12345678", 4321, 0x41, 0x20)
        remote = CanMessage(0x7FF, False, True, 3, b"", 4567, 2, 0)
        err = QueueTransport()
        err.open()
        self.assertTrue(err.metadata["connected"])
        for item in (frame, remote):
            self.assertEqual(loopback_frame(item.event(), item.timestamp_ns), item)
            self.assertEqual(model_frame(item.event(), item.timestamp_ns), item)
            err.write_frame(item, timeout=.1)
        self.assertEqual(err.read_frame(timeout=.1), frame)
        self.assertEqual(err.read_frame(timeout=.1), remote)
        self.assertIsNone(err.read_frame(timeout=.1))
        err.close()
        err.close()
        with self.assertRaises(ConnectionError):
            err.read_frame(timeout=.1)


class Serial(unittest.TestCase):
    def run_backend(self, backend, count):
        master, device = pty.openpty()
        tty.setraw(device)
        address = os.ttyname(device)
        observer = []
        options = {"ready": lambda sequence: observer.append({"ready": sequence})} if backend is PtyTransport else {}
        pair = backend(SerialConfig(address, inter_byte_timeout=.03), observer.append, **options)
        try:
            pair.open()
            self.assertEqual(pair.metadata["backend"], backend.backend)
            self.assertEqual(pair.read(3, timeout=.02), b"")
            if options:
                pair.prepare(99)
                self.assertEqual(observer[-1], {"ready": 99})
            for n in range(count):
                pair.correlation = n
                packet = struct.pack(">I", n) + bytes((n + i) % 256 for i in range(n % 21))
                self.assertEqual(pair.write(packet), len(packet))
                self.assertEqual(read_exact(lambda k: os.read(master, k), len(packet)), packet)
                reply = packet[::-1]
                split = 1 + n % (len(reply) - 1)
                os.write(master, reply[:split])
                first = pair.read(split)
                os.write(master, reply[split:])
                answer = first + read_exact(pair.read, len(reply) - len(first))
                self.assertEqual(answer, reply)
                if n in (0, count - 1):
                    sample("serial", backend=backend.backend, sequence=n,
                           tx=packet.hex(), rx=answer.hex(), observed=observer[-5:])
            os.close(master)
            master = None
            with self.assertRaises(OSError):
                pair.read(1, timeout=.1)
            self.assertFalse(pair.connected)
            pair.close()
            new_master, new_device = pty.openpty()
            with self.assertRaises(OSError):
                pair.open()
            try:
                with backend(SerialConfig(os.ttyname(new_device))) as reconnected:
                    self.assertEqual(reconnected.write(b"reconnect"), 9)
                    self.assertEqual(os.read(new_master, 9), b"reconnect")
            finally:
                os.close(new_master)
                os.close(new_device)
        finally:
            pair.close()
            if master is not None:
                os.close(master)
            os.close(device)
        sample("serial_totals", classification="SERIAL_BACKEND_ON_PTY" if backend is SerialTransport else "PTY",
               count=count, mismatches=0, timeout=True, disconnect=True, reconnect=True)

    def test_serial_on_pty_thousand_exchanges(self):
        self.run_backend(SerialTransport, 1000)

    def test_pty_contract_ready_and_wire(self):
        self.run_backend(PtyTransport, 12)

    def test_unavailable_port_does_not_fallback(self):
        channel = SerialTransport(SerialConfig("/dev/vel-no-such-port"))
        with self.assertRaises(OSError):
            channel.open()
        self.assertFalse(channel.connected)
        self.assertEqual(channel.metadata["backend"], "serial")


class TCP(unittest.TestCase):
    def test_configured_tcp_thousand_exchanges_and_faults(self):
        errors = []
        count = 1000
        with closing(socket.socket()) as listener:
            listener.bind(("127.0.0.2", 0))
            listener.listen()
            listener.settimeout(8)
            config = TcpConfig("127.0.0.2", listener.getsockname()[1], .5, .3, .3)
            def server():
                try:
                    with closing(listener.accept()[0]) as peer:
                        peer.settimeout(4)
                        for index in range(0, count, 2):
                            a = read_exact(peer.recv, 8)
                            b = read_exact(peer.recv, 8)
                            self.assertEqual(a, struct.pack(">II", index, index ^ 254))
                            self.assertEqual(b, struct.pack(">II", index + 1, (index + 1) ^ 254))
                            # Separate first byte, then combine the two replies.
                            both = a[::-1] + b[::-1]
                            peer.sendall(both[:1])
                            peer.sendall(both[1:])
                        self.assertEqual(peer.recv(1), b"")
                        peer.sendall(b"END")
                        peer.shutdown(socket.SHUT_WR)
                    with closing(listener.accept()[0]) as peer:
                        peer.settimeout(4)
                        peer.recv(1)
                        peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                except Exception as error:
                    errors.append(error)
            th = threading.Thread(target=server)
            th.start()
            tcp = TcpTransport(config)
            try:
                tcp.open()
                self.assertEqual(tcp.read(8, timeout=.025), b"")
                for index in range(0, count, 2):
                    packed = [struct.pack(">II", i, i ^ 254) for i in (index, index + 1)]
                    tcp.write(packed[0][:3])
                    tcp.write(packed[0][3:] + packed[1])
                    first = read_exact(tcp.read, 8)
                    second = read_exact(tcp.read, 8)
                    self.assertEqual([first, second], [x[::-1] for x in packed])
                    if index in (0, count - 2):
                        sample("tcp", sequence=index, tx=packed[0].hex(), rx=first.hex())
                tcp.shutdown(socket.SHUT_WR)
                self.assertEqual(read_exact(tcp.read, 3), b"END")
                with self.assertRaises(ConnectionError):
                    tcp.read(1)
                self.assertFalse(tcp.connected)
                tcp.open()
                tcp.write(b"r")
                with self.assertRaises(ConnectionResetError):
                    tcp.read(1)
                self.assertFalse(tcp.connected)
            finally:
                tcp.close()
                th.join(10)
            self.assertFalse(th.is_alive())
            self.assertEqual(errors, [])
        with self.assertRaises(OSError):
            tcp.open()
        self.assertFalse(tcp.connected)
        sample("tcp_totals", endpoint=config.host, count=count, mismatches=0,
               timeout=True, half_close=True, rst=True, refused=True, reconnect=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
