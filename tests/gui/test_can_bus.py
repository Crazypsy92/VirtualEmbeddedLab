"""Unit tests, subprocess acceptance, and WSLg acceptance for the Host CAN model."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vel_can_bus import live_bus
from vel_can_bus_model import ACTIVE, BUS_OFF, NODES, PASSIVE, RECOVERING, Confinement, arbitrate
from vel_can_frames import CanFrame
from vel_env import work


def frame(id_, extended=False, data=b"\x55"):
    return CanFrame(id_, extended, len(data), data)


def events(path, kind=None):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return [row for row in rows if kind is None or row["kind"] == kind]


class Model(unittest.TestCase):
    def test_base_id_and_standard_extended_shared_base(self):
        outcome = arbitrate({"A": frame(0x13), "B": frame(0x12), "C": frame(0x14)})
        self.assertEqual(outcome["leaders"], ["B"])
        self.assertEqual(outcome["retry"], ["A", "C"])
        self.assertEqual(outcome["comparisons"][0]["bit"], 10)
        outcome = arbitrate({"A": frame(0x321), "B": frame((0x321 << 18) | 1, True)})
        self.assertEqual(outcome["leaders"], ["A"])
        self.assertEqual(outcome["comparisons"][0], {"node": "B", "bit": 11, "field": "RTR/SRR",
                                                     "winner_bit": 0, "loser_bit": 1})
        self.assertEqual(arbitrate({"A": frame(0x321), "B": frame(0x320 << 18, True)})["leaders"], ["B"])

    def test_same_arbitration_field_conflict_and_identical(self):
        self.assertTrue(arbitrate({"A": frame(1), "B": frame(1, data=b"\xff")})["conflict"])
        self.assertFalse(arbitrate({"A": frame(1), "B": frame(1)})["conflict"])

    def test_confinement_thresholds_and_idle(self):
        model = Confinement(127, 127)
        self.assertEqual(model.state, ACTIVE)
        model.fault("rx")
        self.assertEqual((model.state, model.rec), (PASSIVE, 128))
        model.fault("ack")
        self.assertEqual(model.tec, 127)
        model.valid_rx()
        self.assertEqual((model.state, model.rec), (ACTIVE, 127))
        model.tec = 248
        model.fault("tx")
        self.assertEqual((model.tec, model.state), (256, BUS_OFF))
        model.start_recovery()
        model.idle(127)
        self.assertEqual((model.state, model.remaining), (RECOVERING, 1))
        model.idle(1)
        self.assertEqual((model.state, model.tec, model.rec), (ACTIVE, 0, 0))
        model.acknowledge_tx()
        model.valid_rx()
        self.assertEqual((model.tec, model.rec), (0, 0))


class IPC(unittest.TestCase):
    def folder(self):
        base = work("can-h2-test")
        base.mkdir(parents=True, exist_ok=True)
        folder = Path(mkdtemp(prefix=f"{self._testMethodName}-", dir=base))
        print(f"IPC evidence {folder}", flush=True)
        return folder

    def boot(self, bus):
        for node in NODES:
            bus.start(node)
        pids = {v["pid"] for v in bus.states().values()}
        self.assertEqual(len(pids), 3)
        self.assertNotIn(os.getpid(), pids)
        self.assertTrue(all(Path(f"/proc/{p}").exists() for p in pids))
        return pids

    def clean(self, pids):
        self.assertFalse(any(Path(f"/proc/{p}").exists() for p in pids))

    def test_message_delivery_filter_and_rejoin(self):
        folder = self.folder()
        expected = []
        with live_bus(folder) as bus:
            pids = self.boot(bus)
            for i in range(1002):
                source = NODES[i % 3]
                dlc = i % 9
                is_extended = bool(i % 2)
                value = frame(i + (0x10000 if is_extended else 0), is_extended,
                              bytes((i + j * 29) % 256 for j in range(dlc)))
                expected.extend((source, target, value.fields()) for target in NODES if target != source)
                bus.transmit({source: value})
            for node in bus.states().values():
                self.assertEqual((node["tx"], node["rx"], node["filtered"]), (334, 668, 0))
            bus.set_filter("C", "standard", 0x120, 0x7f0)
            bus.transmit({"A": frame(0x122)})
            bus.transmit({"A": frame(0x132)})
            bus.transmit({"A": frame(0x122, True)})
            before = bus.states()["C"]
            self.assertEqual((before["rx"], before["filtered"]), (669, 2))
            bus.stop("C")
            self.assertFalse(Path(f"/proc/{before['pid']}").exists())
            bus.transmit({"A": frame(0x122)})
            bus.start("C")
            new = bus.states()["C"]
            self.assertNotEqual(new["pid"], before["pid"])
            self.assertEqual((new["rx"], new["filter"]), (before["rx"], before["filter"]))
            pids.add(new["pid"])
            bus.transmit({"B": frame(0x122)})
            self.assertEqual(bus.states()["C"]["rx"], 670)
        self.clean(pids)
        log = folder / "can-bus.jsonl"
        got = events(log, "delivered")
        self.assertEqual([(e["source_node"], e["target_node"], e["frame"]) for e in got[:2004]], expected)
        self.assertEqual([(e["round"], e["target_node"]) for e in got],
                         list(dict.fromkeys((e["round"], e["target_node"]) for e in got)))
        rows = events(log, "transaction")
        self.assertEqual(rows[1002]["targets"], ["B", "C"])
        self.assertEqual([rows[i]["filtered"] for i in (1003, 1004)], [["C"], ["C"]])
        self.assertEqual(rows[1005]["excluded"], {"C": "OFFLINE"})
        self.assertEqual(rows[1006]["targets"], ["A", "C"])

    def test_contested_rounds_and_retry(self):
        folder = self.folder()
        with live_bus(folder) as bus:
            pids = self.boot(bus)
            for i in range(36):
                bus.transmit({"A": frame(0x210 + i), "B": frame(0x100 + i), "C": frame(0x300 + i)})
                bus.transmit({"A": frame(0x123), "B": frame((0x123 << 18) | i, True)})
                a, b, c = (NODES[(i + k) % 3] for k in range(3))
                bus.transmit({a: frame(0x200), b: frame(0x200, data=b"\xAA"), c: frame(0x400)})
        self.clean(pids)
        log = folder / "can-bus.jsonl"
        rounds = events(log, "arbitration")
        transactions = {x["round"]: x for x in events(log, "transaction")}
        offset = 0
        for i in range(36):
            normal, mid, tail, format_, ext, conflict, remaining = rounds[offset:offset + 7]
            offset += 7
            self.assertEqual((normal["leaders"], mid["leaders"], tail["leaders"]), (["B"], ["A"], ["C"]))
            self.assertEqual((normal["retry"], mid["retry"]), (["A", "C"], ["C"]))
            self.assertEqual((format_["leaders"], ext["leaders"]), (["A"], ["B"]))
            self.assertEqual(format_["comparisons"][0]["field"], "RTR/SRR")
            self.assertTrue(conflict["conflict"])
            self.assertEqual(transactions[conflict["round"]]["status"], "CONFLICT")
            self.assertEqual(transactions[conflict["round"]]["targets"], [])
            self.assertEqual(remaining["leaders"], conflict["retry"])
        self.assertEqual(len(rounds), 252)
        self.assertEqual(sum(len(r["candidates"]) >= 2 for r in rounds), 144)

    def test_fault_confinement_recovery_with_live_peers(self):
        folder = self.folder()
        with live_bus(folder) as bus:
            pids = self.boot(bus)
            bus.add_fault("A", "ack", 20)
            for _ in range(20):
                bus.transmit({"A": frame(1)})
            self.assertEqual((bus.states()["A"]["state"], bus.states()["A"]["tec"]), (PASSIVE, 128))
            bus.add_fault("A", "tx", 16)
            for _ in range(16):
                bus.transmit({"A": frame(1)})
            self.assertEqual(bus.states()["A"]["state"], BUS_OFF)
            bus.transmit({"A": frame(1)})
            bus.stop("A")
            bus.start("A")
            pids.add(bus.states()["A"]["pid"])
            self.assertEqual(bus.states()["A"]["state"], BUS_OFF)
            bus.transmit({"B": frame(2)})
            self.assertEqual(bus.states()["C"]["rx"], 1)
            bus.add_fault("B", "rx", 1)
            bus.transmit({"C": frame(3)})
            self.assertEqual(bus.states()["B"]["rec"], 1)
            bus.recover("A")
            bus.idle("A", 127)
            self.assertEqual(bus.states()["A"]["state"], RECOVERING)
            bus.transmit({"A": frame(1)})
            bus.idle("A", 1)
            self.assertEqual((bus.states()["A"]["state"], bus.states()["A"]["tec"]), (ACTIVE, 0))
            bus.transmit({"A": frame(1)})
            self.assertEqual(bus.states()["B"]["rec"], 0)
        self.clean(pids)
        log = folder / "can-bus.jsonl"
        self.assertEqual([e["status"] for e in events(log, "rejected")], [BUS_OFF, RECOVERING])
        state = events(log, "state")
        transitions = [(x["before"]["state"], x["after"]["state"]) for x in state
                       if x["source_node"] == "A" and x["before"]["state"] != x["after"]["state"]]
        self.assertEqual(transitions, [(ACTIVE, PASSIVE), (PASSIVE, BUS_OFF), (BUS_OFF, RECOVERING), (RECOVERING, ACTIVE)])
        tx = events(log, "transaction")
        self.assertEqual(Counter(row["status"] for row in tx),
                         {"ACK_MISSING": 21, "TX_ERROR": 16, "PASS": 2})
        self.assertEqual(tx[-1]["targets"], ["B", "C"])


class Window(unittest.TestCase):
    def test_real_wslg_multinode_arbitration_and_recovery(self):
        self.assertTrue(os.environ.get("DISPLAY"), "A real WSLg display is required")
        import tkinter as tk
        from vel_gui_workbench import Workbench
        from vel_jobs import lock_status
        root = tk.Tk()
        app = Workbench(root)
        root.geometry("1250x900+20+20")
        stage = 0
        errors = []
        folder = None
        supervisor = None
        restarted = None
        pids = set()
        deadline = time.monotonic() + 90

        def pick(panel, active):
            for node, info in panel.frames.items():
                info[0].set(node in active)

        def check():
            nonlocal stage, folder, supervisor, restarted
            try:
                self.assertLess(time.monotonic(), deadline, (stage, app.status.get()))
                if stage == 0 and app.available is not None:
                    app.select("CAN")
                    self.assertEqual(app.mode.get(), "交互会话")
                    app.mode.set("多节点总线")
                    app.mode_picker.event_generate("<<ComboboxSelected>>")
                    self.assertEqual(str(app.start_button["state"]), "normal")
                    app.start_button.invoke()
                    folder, supervisor = app.folder, app.job.pid
                    stage = 1
                elif stage == 11 and not app.job:
                    self.assertTrue(all(panel[-1][0].get() == "离线" for panel in app.can_panel.frames.values()))
                    first = json.loads((folder / "result.json").read_text())
                    self.assertFalse(any(Path(f"/proc/{p}").exists() for p in {*pids, supervisor, first["pid"]}))
                    self.assertFalse(lock_status(work("gui-h1/locks") / "can.lock")[0])
                    app.start_button.invoke()
                    restarted = (app.folder, app.job.pid)
                    stage = 12
                elif stage == 12 and app.live:
                    app.close()
                    stage = 13
                    return
                elif 1 <= stage <= 10 and app.live and not app.pending:
                    panel = app.can_panel
                    if stage == 1:
                        pick(panel, NODES)
                        panel.transmit.invoke()
                    elif stage == 2:
                        self.assertEqual(len(panel.rounds), 3)
                        self.assertEqual(panel.rounds["1"]["leaders"], ["A"])
                        self.assertEqual(panel.rounds["1"]["retry"], ["B", "C"])
                        panel.arbitration.selection_set("1")
                        panel.show_round()
                        self.assertIn("0 显性", panel.detail.get())
                        panel.inject()
                    elif stage == 3:
                        pick(panel, ("A",))
                        panel.count.set("32")
                        panel.transmit.invoke()
                    elif stage == 4:
                        self.assertIn("Bus-Off", panel.frames["A"][-1][0].get())
                        output = os.environ.get("VEL_H2_SCREENSHOTS")
                        if output:
                            panel.transactions.yview_moveto(0)
                            panel.arbitration.see("1")
                            for idx, name in enumerate(("transactions", "arbitration", "errors")):
                                panel.tabs.select(idx)
                                root.update()
                                root.after(100)
                                root.update()
                                subprocess.run(["import", "-window", hex(root.winfo_id()),
                                                str(Path(output) / f"{name}.png")], check=True, timeout=10)
                        panel.count.set("1")
                        panel.transmit.invoke()
                    elif stage == 5:
                        panel.action("recover")
                    elif stage == 6:
                        self.assertIn("Recovery", panel.frames["A"][-1][0].get())
                        panel.action("idle", groups=128)
                    elif stage == 7:
                        self.assertIn("Error Active", panel.frames["A"][-1][0].get())
                        panel.transmit.invoke()
                    elif stage == 8:
                        panel.selected.set("C")
                        panel.stop.invoke()
                    elif stage == 9:
                        self.assertEqual(panel.frames["C"][-1][0].get(), "离线")
                        panel.start.invoke()
                    elif stage == 10:
                        observed = events(folder / "can-bus.jsonl", "node")
                        pids.update(x["node"]["pid"] for x in observed if x["node"]["pid"])
                        self.assertEqual(len(pids), 4)
                        app.stop.invoke()
                    stage += 1
            except Exception as error:
                errors.append(error)
                app.close()
                return
            root.after(180, check)

        root.after(150, check)
        root.mainloop()
        if errors:
            raise errors[0]
        self.assertEqual(stage, 13)
        second, pid = restarted
        closing = json.loads((second / "result.json").read_text())
        pids.update(x["node"]["pid"] for x in events(second / "can-bus.jsonl", "node") if x["node"]["pid"])
        self.assertEqual(len(pids), 7)
        self.assertFalse(any(Path(f"/proc/{p}").exists() for p in (pid, closing["pid"])))
        result = json.loads((folder / "result.json").read_text())
        self.assertEqual(result["status"], "CANCELLED")
        self.assertFalse(any(Path(f"/proc/{pid}").exists() for pid in {*pids, supervisor, result["pid"]}))
        self.assertFalse(lock_status(work("gui-h1/locks") / "can.lock")[0])
        rows = events(folder / "can-bus.jsonl", "transaction")
        self.assertEqual(rows[-1]["status"], "PASS")
        self.assertEqual(rows[-1]["targets"], ["B", "C"])
        self.assertEqual(len(events(folder / "can-bus.jsonl", "rejected")), 1)
        print(f"WSLg CAN-H2 evidence {folder}", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
