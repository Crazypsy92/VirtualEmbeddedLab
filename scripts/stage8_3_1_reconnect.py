"""Reproduce a reconnect while all four client contexts are occupied."""
from contextlib import ExitStack, closing
import os
from pathlib import Path
import signal
import struct
from stage8_3_runtime import frame, receive, wait_for


def full_slot_reconnect(lab):
    with ExitStack() as resources:
        clients = [resources.enter_context(closing(lab.raw())) for _ in range(4)]
        read = struct.pack(">HH", 1, 1)
        for i, client in enumerate(clients, 920):
            client.sendall(frame(i, 1, 3, read))
            assert receive(client) == (i, 1, b"\x03\x02\x00\x0a")
        wait_for(lambda: any("connections=4" in line for line in lab.gateway_log.read_text().splitlines()
                             if line.startswith("GW_STATS")), 2)
        # Both the FIN and the pending connection become visible to the
        # gateway in the same poll cycle. No traffic leaves loopback.
        os.killpg(lab.gateway.pid, signal.SIGSTOP)
        try:
            wait_for(lambda: "\nState:\tT " in Path(f"/proc/{lab.gateway.pid}/status").read_text(), 1)
            retiring = clients[0]
            retiring.close()
            replacement = resources.enter_context(closing(lab.raw()))
            replacement.sendall(frame(924, 1, 3, read))
        finally:
            os.killpg(lab.gateway.pid, signal.SIGCONT)
        assert receive(replacement) == (924, 1, b"\x03\x02\x00\x0a")
        for i, client in enumerate(clients[1:], 925):
            client.sendall(frame(i, 1, 3, read))
            assert receive(client) == (i, 1, b"\x03\x02\x00\x0a")
        return {"name": "reconnect_with_four_slots_occupied", "status": "PASS",
                "retired_tid": 920, "replacement_tid": 924, "unaffected_tids": [925, 926, 927]}
