"""Tk controls for three independent processes on the Host CAN bus model."""
import json
import tkinter as tk
from tkinter import ttk

from vel_can_bus_model import NODES
from vel_can_frames import parse_fields


def hexdump(value):
    return " ".join(value[i:i + 2] for i in range(0, len(value), 2)).upper()


class BusPanel(ttk.Frame):
    def __init__(self, parent, tree, send):
        super().__init__(parent, padding=(4, 4))
        self.send = send
        self.path = None
        self.offset = 0
        self.frames = {}
        self.actions = []
        self.rounds = {}
        self.selected = tk.StringVar(value="A")
        self.message = tk.StringVar(value="Host CAN Bus Model · 启动后创建 A / B / C 节点进程")
        self.detail = tk.StringVar()
        ttk.Label(self, textvariable=self.message, wraplength=870).pack(fill="x")
        control = ttk.Frame(self)
        control.pack(fill="x", pady=(3, 2))
        self.combo(control, self.selected, NODES, 4).pack(side="left", padx=(0, 4))
        self.start = self.button(control, "启动节点", lambda: self.action("start"))
        self.stop = self.button(control, "停止节点", lambda: self.action("stop"))
        self.button(control, "申请恢复", lambda: self.action("recover"))
        self.button(control, "推进 128 空闲组", lambda: self.action("idle", groups=128))
        self.fault = tk.StringVar(value="tx")
        self.combo(control, self.fault, ("tx", "ack", "rx"), 5).pack(side="left", padx=(8, 3))
        self.fault_count = self.entry(control, "32", 4)
        self.button(control, "注入故障", self.inject)

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=2)
        ttk.Label(filters, text="选中节点的接收过滤  IDE").pack(side="left")
        self.filter_format = tk.StringVar(value="all")
        self.combo(filters, self.filter_format, ("all", "standard", "extended"), 9).pack(side="left", padx=3)
        ttk.Label(filters, text="ID / Mask (HEX)").pack(side="left", padx=3)
        self.filter_id = self.entry(filters, "0", 7)
        self.filter_mask = self.entry(filters, "0", 7)
        self.button(filters, "应用过滤", self.filter)

        rows = ttk.Frame(self)
        rows.pack(fill="x")
        fields = (("节点", 0), ("帧格式", 1), ("ID (HEX)", 2), ("DLC", 3), ("DATA (HEX)", 4),
                  ("状态 / PID", 5), ("TX / RX / 过滤", 6), ("TEC / REC", 7))
        for label, column in fields:
            ttk.Label(rows, text=label).grid(row=0, column=column, sticky="w", padx=4)
        for index, node in enumerate(NODES, 1):
            enabled = tk.BooleanVar(value=index < 3)
            ttk.Checkbutton(rows, text=node, variable=enabled).grid(row=index, column=0, sticky="w")
            format_ = tk.StringVar(value="Standard")
            self.combo(rows, format_, ("Standard", "Extended"), 10).grid(row=index, column=1, padx=4)
            params = [tk.StringVar(value=value) for value in (f"{index * 0x100:X}", "1", f"0{index}")]
            for column, (var, width) in enumerate(zip(params, (10, 4, 23)), 2):
                ttk.Entry(rows, textvariable=var, width=width).grid(row=index, column=column, sticky="w", padx=4)
            values = [tk.StringVar(value="—") for _ in range(3)]
            for column, var in enumerate(values, 5):
                ttk.Label(rows, textvariable=var, width=(25 if column == 5 else 13)).grid(
                    row=index, column=column, sticky="w", padx=4)
            self.frames[node] = (enabled, format_, *params, values)

        transmit = ttk.Frame(self)
        transmit.pack(fill="x", pady=4)
        ttk.Label(transmit, text="勾选同轮争用的发送节点").pack(side="left", padx=(0, 8))
        ttk.Label(transmit, text="轮次").pack(side="left")
        self.count = self.entry(transmit, "1", 5)
        self.transmit = self.button(transmit, "发送 / 同时发送", self.submit)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        bus, arbitration, errors = [ttk.Frame(self.tabs) for _ in range(3)]
        for tab, label in ((bus, "总线事务"), (arbitration, "仲裁详情"), (errors, "错误与状态时间线")):
            self.tabs.add(tab, text=label)
        self.transactions = tree(bus, [("seq", "#", 45), ("round", "轮", 50), ("tx", "发送", 54),
                                       ("rx", "接收", 86), ("id", "ID / IDE", 108), ("size", "DLC", 47),
                                       ("data", "DATA", 157), ("result", "结果", 166)], 7)
        ttk.Label(arbitration, textvariable=self.detail, wraplength=830).pack(fill="x")
        self.arbitration = tree(arbitration, [("round", "轮", 54), ("candidates", "候选", 89),
                                             ("winner", "获胜", 82), ("retry", "下轮重试", 100),
                                             ("reason", "比较依据", 410)], 7)
        self.arbitration.bind("<<TreeviewSelect>>", self.show_round)
        self.errors = tree(errors, [("seq", "#", 48), ("time", "Host +ms", 77), ("node", "节点", 48),
                                    ("reason", "原因", 160), ("before", "之前", 162),
                                    ("after", "之后", 148), ("counters", "TEC / REC", 96)], 7)
        self.set_active(False)

    @staticmethod
    def combo(parent, variable, values, width):
        return ttk.Combobox(parent, state="readonly", textvariable=variable, values=values, width=width)

    @staticmethod
    def entry(line, value, width):
        variable = tk.StringVar(value=value)
        ttk.Entry(line, textvariable=variable, width=width).pack(side="left", padx=4)
        return variable

    def button(self, parent, label, callback):
        widget = ttk.Button(parent, text=label, command=callback)
        widget.pack(side="left", padx=3)
        self.actions.append(widget)
        return widget

    def set_active(self, active):
        for widget in self.actions:
            widget.configure(state="normal" if active else "disabled")

    def outcome(self, event):
        self.message.set("Host CAN Bus Model · " + event.get("reason",
                         "总线指令已完成" if "counts" in event else "节点进程已连接"))

    def action(self, op, **fields):
        self.send({"op": op, "node": self.selected.get(), **fields})

    def inject(self):
        try:
            count = int(self.fault_count.get())
        except ValueError:
            self.message.set("故障次数请输入整数")
            return
        self.action("fault", kind=self.fault.get(), count=count)

    def filter(self):
        self.action("filter", format=self.filter_format.get(), id=self.filter_id.get(), mask=self.filter_mask.get())

    def submit(self):
        offers = {}
        try:
            count = int(self.count.get())
            for node, (enabled, format_, id_, dlc, data, _) in self.frames.items():
                if enabled.get():
                    fields = dict(format=format_.get(), id=id_.get(), dlc=dlc.get(), data=data.get())
                    parse_fields(*fields.values())
                    offers[node] = fields
            if not offers or not 1 <= count <= 64:
                raise ValueError("勾选发送节点并输入 1–64 轮")
        except ValueError as error:
            self.message.set(str(error))
            return
        self.send({"op": "send", "offers": offers, "count": count})

    def update_log(self, path):
        if path != self.path:
            self.path, self.offset, self.origin = path, 0, None
            self.rounds.clear()
            for table in (self.transactions, self.arbitration, self.errors):
                table.delete(*table.get_children())
            self.detail.set("")
            for *_, cells in self.frames.values():
                for cell in cells:
                    cell.set("—")
        if path is None or not path.is_file():
            return
        with path.open("rb") as log:
            log.seek(self.offset)
            while line := log.readline():
                if not line.endswith(b"\n"):
                    break
                self.offset = log.tell()
                self.add(json.loads(line))

    @staticmethod
    def insert(table, values, **kwargs):
        iid = table.insert("", "end", values=values, **kwargs)
        table.see(iid)

    def add(self, event):
        kind, seq = event["kind"], event["sequence"]
        if self.origin is None:
            self.origin = event["monotonic_ns"]
        if kind == "snapshot":
            for key, node in event["nodes"].items():
                status, counts, counters = self.frames[key][-1]
                status.set(f"{node['state']} · {node['pid']}" if node["online"] else "离线")
                counts.set(f"{node['tx']} / {node['rx']} / {node['filtered']}")
                counters.set(f"{node['tec']} / {node['rec']}")
        elif kind in ("transaction", "rejected"):
            frame = event.get("frame", {})
            sources = event.get("source_nodes", [event["source_node"]])
            filtered = event.get("filtered", [])
            extra = f" · 过滤 {','.join(filtered)}" if filtered else ""
            self.insert(self.transactions, (seq, event.get("round", "—"), ",".join(sources),
                ",".join(event.get("targets", [])) or "—",
                f"0x{frame['id']:X} / {int(frame['ide'])}" if frame else "—",
                frame.get("dlc", "—"), hexdump(frame.get("data", "")) or "—", event["status"] + extra))
        elif kind == "arbitration":
            key = str(event["round"])
            self.rounds[key] = event
            reasons = "; ".join(f"{x['node']} · {x['field']} 位 {x['bit']}: 0 优先于 1"
                                for x in event["comparisons"])
            status = ("同仲裁字段，载荷冲突" if event["conflict"] else reasons or "无优先级冲突")
            self.insert(self.arbitration, (key, ",".join(event["fields"]),
                        "—" if event["conflict"] else ",".join(event["leaders"]),
                        ",".join(event["retry"]) or "—", status), iid=key)
            if not self.arbitration.selection():
                self.arbitration.selection_set(key)
        elif kind in ("state", "fault", "node"):
            before, after = event.get("before", {}), event.get("after", event.get("node", {}))
            elapsed = (event["monotonic_ns"] - self.origin) / 1e6
            reason = event.get("reason", f"{event.get('fault', '')} × {event.get('count', '')}")
            counter = f"{after['tec']} / {after['rec']}" if after else "—"
            self.insert(self.errors, (seq, f"{elapsed:.2f}", event.get("source_node", after.get("node")),
                        reason, before.get("state", "—"), after.get("state", "—"), counter))

    def show_round(self, _event=None):
        selected = self.arbitration.selection()
        if selected:
            event = self.rounds[selected[0]]
            summary = "   ".join(f"{node}: {bits}" for node, bits in event["fields"].items())
            if event["conflict"]:
                summary += "   · 同仲裁字段，数据阶段冲突"
            self.detail.set("逻辑仲裁位（0 显性，1 隐性）  " + summary)
