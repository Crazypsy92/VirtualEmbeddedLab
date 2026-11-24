"""Deterministic parts of the Classical CAN data-frame experiment."""
from dataclasses import dataclass
from vel_can_frames import CanFrame

NODES = ("A", "B", "C")
ACTIVE, PASSIVE, BUS_OFF, RECOVERING = "Error Active", "Error Passive", "Bus-Off", "Recovery"
TEC_PASSIVE, TEC_OFF, IDLE_GROUPS = 128, 256, 128


def arbitration_bits(frame: CanFrame):
    if frame.extended:
        return f"{frame.id >> 18:011b}11{frame.id & 0x3FFFF:018b}0"
    return f"{frame.id:011b}00"


def arbitrate(offers):
    fields = {node: arbitration_bits(frame) for node, frame in offers.items()}
    best = min(fields.values())
    leaders = [node for node, key in fields.items() if key == best]
    losers = [node for node in fields if node not in leaders]
    compared = []
    for node in losers:
        bit = next(i for i, (a, b) in enumerate(zip(best, fields[node])) if a != b)
        name = f"Base ID[{10 - bit}]" if bit < 11 else "RTR/SRR" if bit == 11 else (
            "IDE" if bit == 12 else f"Extended ID[{30 - bit}]")
        compared.append({"node": node, "bit": bit, "field": name, "winner_bit": 0, "loser_bit": 1})
    conflict = any(offers[node] != offers[leaders[0]] for node in leaders[1:])
    return {"fields": fields, "leaders": leaders, "retry": losers,
            "comparisons": compared, "conflict": conflict}


@dataclass
class Confinement:
    tec: int = 0
    rec: int = 0
    remaining: int = 0

    @property
    def state(self):
        if self.remaining:
            return RECOVERING
        if self.tec >= TEC_OFF:
            return BUS_OFF
        return PASSIVE if max(self.tec, self.rec) >= TEC_PASSIVE else ACTIVE

    def acknowledge_tx(self):
        self.tec = max(0, self.tec - 1)

    def valid_rx(self):
        self.rec = 127 if self.rec > 127 else max(0, self.rec - 1)

    def fault(self, kind):
        if kind == "rx":
            self.rec += 1
        elif kind == "tx" or (kind == "ack" and self.state != PASSIVE):
            self.tec = min(TEC_OFF, self.tec + 8)

    def start_recovery(self):
        if self.state != BUS_OFF:
            raise ValueError("仅 Bus-Off 节点可开始恢复")
        self.remaining = IDLE_GROUPS

    def idle(self, groups):
        if self.state != RECOVERING:
            raise ValueError("先启动恢复")
        self.remaining = max(0, self.remaining - groups)
        if not self.remaining:
            self.tec = self.rec = 0
