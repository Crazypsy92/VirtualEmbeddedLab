"""Host CAN bus service with three independently running Python node processes."""
from contextlib import contextmanager
import json
from pathlib import Path
import select
import subprocess
import sys
import time

from vel_can_bus_model import ACTIVE, BUS_OFF, NODES, RECOVERING, arbitrate
from vel_can_frames import CanFrame, parse_fields
from vel_jobs import install_cancel_handlers


class Node:
    def __init__(self, identity, previous):
        self.identity = identity
        self.process = subprocess.Popen(
            [sys.executable, Path(__file__).with_name("vel_can_bus_node.py"), identity],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            self.call("restore", previous=previous)
        except BaseException:
            self.close()
            raise

    def call(self, op, **fields):
        self.process.stdin.write(json.dumps({"op": op, **fields}) + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 2)[0]:
            raise TimeoutError(f"Node {self.identity} IPC 超时")
        reply = self.process.stdout.readline()
        if not reply:
            raise ConnectionError(f"Node {self.identity} IPC 已关闭")
        result = json.loads(reply)
        if result.get("node") != self.identity:
            raise RuntimeError("节点 IPC 身份不匹配")
        if "error" in result:
            raise ValueError(result["error"])
        self.last = result["state"]
        return result

    def close(self):
        try:
            self.process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=2)


class Bus:
    def __init__(self, stream):
        self.stream = stream
        self.nodes = {}
        self.saved = {}
        self.faults = {node: {"ack": 0, "tx": 0, "rx": 0} for node in NODES}
        self.sequence = self.round = 0

    def emit(self, kind, **fields):
        self.sequence += 1
        event = {"kind": kind, "sequence": self.sequence, "monotonic_ns": time.monotonic_ns(),
                 "backend": "Host CAN Bus Model", **fields}
        self.stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.stream.flush()
        return event

    def start(self, identity):
        if identity not in NODES or identity in self.nodes:
            raise ValueError("只能启动离线的 A / B / C 节点")
        node = Node(identity, self.saved.get(identity))
        self.nodes[identity] = node
        self.emit("node", reason="JOIN", node=node.last)

    def stop(self, identity):
        node = self.require(identity)
        self.saved[identity] = node.last | {"online": False, "pid": None}
        node.close()
        del self.nodes[identity]
        self.emit("node", reason="LEAVE", node=self.saved[identity])

    def require(self, identity):
        if identity not in self.nodes:
            raise ValueError(f"Node {identity} 离线")
        return self.nodes[identity]

    def states(self):
        return {key: self.nodes[key].last if key in self.nodes else self.saved.get(
            key, {"node": key, "online": False, "state": ACTIVE, "tec": 0, "rec": 0, "tx": 0,
                  "rx": 0, "filtered": 0, "pid": None, "recovery_remaining": 0}) for key in NODES}

    def update(self, identity, op, *, reason=None, **fields):
        node = self.nodes[identity]
        before = node.last
        result = node.call(op, **fields)
        after = result["state"]
        if reason or any(before[key] != after[key] for key in ("state", "tec", "rec")):
            self.emit("state", source_node=identity, reason=reason or op, before=before, after=after)
        return result

    def consume(self, identity, kind):
        pending = self.faults[identity]
        if pending[kind]:
            pending[kind] -= 1
            return True
        return False

    def add_fault(self, identity, kind, count):
        self.require(identity)
        if kind not in ("ack", "tx", "rx") or type(count) is not int or not 0 <= count <= 1000:
            raise ValueError("故障为 ACK / TX / RX，次数 0–1000")
        self.faults[identity][kind] = count
        self.emit("fault", source_node=identity, fault=kind, count=count)

    def set_filter(self, identity, format_, target, mask):
        self.require(identity)
        if (format_ not in ("all", "standard", "extended") or type(target) is not int or
                type(mask) is not int or not 0 <= target <= 0x1FFFFFFF or not 0 <= mask <= 0x1FFFFFFF):
            raise ValueError("过滤条件必须是有效 IDE 与 29 位 ID / Mask")
        self.update(identity, "filter", reason="FILTER", filter={"format": format_, "id": target, "mask": mask})

    def recover(self, identity):
        self.require(identity)
        self.update(identity, "recover", reason="RECOVERY_REQUEST")

    def idle(self, identity, groups):
        self.require(identity)
        if type(groups) is not int or not 1 <= groups <= 128:
            raise ValueError("模拟空闲组数量为 1–128")
        self.update(identity, "idle", reason=f"IDLE_{groups}", groups=groups)

    def transmit(self, requested):
        pending = {}
        for identity, frame in requested.items():
            state = self.states().get(identity)
            if state is None:
                raise ValueError("节点必须是 A / B / C")
            if not state["online"] or state["state"] in (BUS_OFF, RECOVERING):
                self.emit("rejected", source_node=identity, frame=frame.fields(),
                          status=state["state"] if state["online"] else "OFFLINE")
                continue
            offer = self.nodes[identity].call("offer", frame=frame.fields())["offer"]
            pending[identity] = CanFrame(offer["id"], offer["ide"], offer["dlc"], bytes.fromhex(offer["data"]))
        while pending:
            self.round += 1
            result = arbitrate(pending)
            self.emit("arbitration", round=self.round,
                      candidates={key: value.fields() for key, value in pending.items()}, **result)
            contenders = result["leaders"]
            arbitration_round = self.round
            if result["conflict"]:
                for node in contenders:
                    self.update(node, "fault", kind="tx", reason="PAYLOAD_CONFLICT")
                self.emit("transaction", round=arbitration_round, source_node=contenders[0],
                          source_nodes=contenders, targets=[], status="CONFLICT",
                          alternatives={key: pending[key].fields() for key in contenders})
            else:
                self.deliver(contenders, pending[contenders[0]])
            pending = {key: pending[key] for key in result["retry"]}
        self.emit("snapshot", nodes=self.states())

    def deliver(self, sources, frame):
        source = sources[0]
        state = self.states()
        peers = [node for node, info in state.items() if node not in sources and info["online"]
                 and info["state"] not in (BUS_OFF, RECOVERING)]
        injected_tx = [node for node in sources if self.consume(node, "tx")]
        injected_ack = [node for node in sources if self.consume(node, "ack")]
        rx_faults = []
        recipients = []
        filtered = []
        receivers = []
        if not injected_tx and not injected_ack:
            rx_faults = [node for node in peers if self.consume(node, "rx")]
            receivers = [node for node in peers if node not in rx_faults]
            for node in rx_faults:
                self.update(node, "fault", kind="rx", reason="RX_ERROR")
        status = "TX_ERROR" if injected_tx else "ACK_MISSING" if not receivers else "PASS"
        if status != "PASS":
            for node in sources:
                self.update(node, "fault", kind="tx" if injected_tx else "ack", reason=status)
        else:
            for node in receivers:
                reply = self.update(node, "receive", delivery=self.round, source=source, frame=frame.fields())
                if received := reply.get("received"):
                    if received != {"delivery": self.round, "source": source, "frame": frame.fields()}:
                        raise RuntimeError(f"Node {node} 接收确认内容不符")
                    recipients.append(node)
                    self.emit("delivered", round=self.round, source_node=source, target_node=node, **received)
                else:
                    filtered.append(node)
            for node in sources:
                self.update(node, "sent")
        self.emit("transaction", round=self.round, source_node=source, source_nodes=sources,
                  targets=recipients, filtered=filtered, receive_errors=rx_faults,
                  excluded={node: ("OFFLINE" if not info["online"] else info["state"])
                            for node, info in state.items() if node not in sources and node not in peers},
                  frame=frame.fields(), status=status)

    def close(self):
        for identity in list(self.nodes):
            self.stop(identity)
        self.emit("snapshot", nodes=self.states())


@contextmanager
def live_bus(folder):
    with (folder / "can-bus.jsonl").open("w", encoding="utf-8") as stream:
        bus = Bus(stream)
        try:
            yield bus
        finally:
            bus.close()


def emit_gui(kind, **fields):
    print(json.dumps({"event": kind, **fields}, ensure_ascii=False), flush=True)


def command(bus, data):
    op = data.get("op")
    node = data.get("node")
    if op == "send":
        offers = data.get("offers")
        count = data.get("count", 1)
        if not isinstance(offers, dict) or not 1 <= len(offers) <= 3 or type(count) is not int or not 1 <= count <= 64:
            raise ValueError("选择最多三个节点，次数 1–64")
        requested = {key: parse_fields(v["format"], v["id"], v["dlc"], v["data"])
                     for key, v in offers.items()}
        for _ in range(count):
            bus.transmit(requested)
        return
    elif op == "start":
        bus.start(node)
    elif op == "stop":
        bus.stop(node)
    elif op == "fault":
        bus.add_fault(node, data["kind"], data["count"])
    elif op == "filter":
        bus.set_filter(node, data["format"], int(data["id"], 16), int(data["mask"], 16))
    elif op == "recover":
        bus.recover(node)
    elif op == "idle":
        bus.idle(node, data["groups"])
    else:
        raise ValueError("未知总线操作")
    bus.emit("snapshot", nodes=bus.states())


def run(folder):
    with live_bus(folder) as bus:
        for node in NODES:
            bus.start(node)
        bus.emit("snapshot", nodes=bus.states())
        emit_gui("can_ready")
        while line := sys.stdin.buffer.readline(4097):
            if not line.endswith(b"\n"):
                raise ValueError("总线请求超长或未结束")
            try:
                command(bus, json.loads(line))
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                bus.emit("command_error", error=str(error))
                emit_gui("can_error", reason=str(error))
            else:
                emit_gui("can_result", counts={"完成": 1})


if __name__ == "__main__":
    install_cancel_handlers()
    try:
        run(Path(sys.argv[1]))
    except Exception as error:
        emit_gui("can_error", reason=str(error))
        sys.exit(1)
