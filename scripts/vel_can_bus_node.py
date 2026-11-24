"""Process-local CAN node state. Receive events acknowledge actual IPC delivery."""
import json
import os
import sys

from vel_can_bus_model import Confinement


def dispatch(identity, command, config, stats, fault):
    op = command["op"]
    if op == "restore" and (previous := command.get("previous")):
        config.update(previous["filter"])
        stats.update({key: previous[key] for key in stats})
        fault.tec, fault.rec, fault.remaining = (previous[key] for key in ("tec", "rec", "recovery_remaining"))
    elif op == "filter":
        config.update(command["filter"])
    elif op == "fault":
        fault.fault(command["kind"])
    elif op == "recover":
        fault.start_recovery()
    elif op == "idle":
        fault.idle(command["groups"])
    elif op == "sent":
        stats["tx"] += 1
        fault.acknowledge_tx()
    result = {"node": identity}
    if op == "offer":
        result["offer"] = command["frame"]
    if op == "receive":
        frame = command["frame"]
        fault.valid_rx()
        accepted = (config["format"] in ("all", "extended" if frame["ide"] else "standard") and
                    frame["id"] & config["mask"] == config["id"] & config["mask"])
        if accepted:
            stats["rx"] += 1
            result["received"] = {"delivery": command["delivery"], "source": command["source"], "frame": frame}
        else:
            stats["filtered"] += 1
    result["state"] = {"node": identity, "online": True, "pid": os.getpid(), **stats,
                       "state": fault.state, "tec": fault.tec, "rec": fault.rec,
                       "recovery_remaining": fault.remaining, "filter": config}
    return result


def main(identity):
    config = {"format": "all", "id": 0, "mask": 0}
    stats = {"tx": 0, "rx": 0, "filtered": 0}
    fault = Confinement()
    for line in sys.stdin:
        try:
            result = dispatch(identity, json.loads(line), config, stats, fault)
        except ValueError as error:
            result = {"node": identity, "error": str(error)}
        print(json.dumps(result, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
