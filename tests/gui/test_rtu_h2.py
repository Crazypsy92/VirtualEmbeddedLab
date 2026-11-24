"""Check UART formatting and grouping of observed RS-485 direction events."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from vel_rtu_layers import BIT_US, CHAR_US, direction_event, host_events, uart_bits


class Layers(unittest.TestCase):
    def test_uart_8e1_known_vectors(self):
        for byte, expected in ((0x00, "00000000001"), (0x01, "01000000011"),
                               (0x55, "01010101001"), (0x80, "00000000111"),
                               (0xFF, "01111111101")):
            with self.subTest(byte=byte):
                self.assertEqual("".join(map(str, uart_bits(byte))), expected)

    def test_theoretical_duration(self):
        self.assertAlmostEqual(BIT_US, 8.6805556, places=6)
        self.assertAlmostEqual(CHAR_US, 95.4861111, places=6)

    def test_parse_firmware_and_host_times_separately(self):
        event = direction_event("RTU_EVENT id=2 sim_ms=320 event=GPIO de=1 re=0")
        self.assertEqual(event, {"sequence": 2, "sim_ms": 320, "kind": "GPIO", "de": 1, "re": 0})
        self.assertIsNone(direction_event("RTU_EVENT id=2 sim_ms=320 event=GPIO de=5 re=0"))
        self.assertEqual([time for _, time in host_events({
            "monotonic_ns": 1000000, "tx_ns": 2000000, "finished_ns": 153000000,
            "rx_ns": None, "status": "TIMEOUT"})], [1, 152])


if __name__ == "__main__":
    unittest.main(verbosity=2)
