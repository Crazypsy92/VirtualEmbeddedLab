"""Tk interaction, frame table and comparison for the native_sim CAN experiment."""
from collections import Counter
import json
import tkinter as tk
from tkinter import ttk

from vel_can_frames import parse_request


def as_hex(data):
    return " ".join(data[i:i + 2] for i in range(0, len(data), 2)).upper()


class CanPanel(ttk.Frame):
    def __init__(self, parent, tree, send):
        super().__init__(parent, padding=(4, 6))
        self.send = send
        self.form = {}
        self.rows = {}
        self.path = None
        self.offset = 0
        self.origin = None
        self.counters = Counter()
        self.message = tk.StringVar(value="启动交互会话后可发送帧。")
        self.totals = tk.StringVar()
        self.decimal = tk.StringVar(value="DEC 291")
        line = ttk.Frame(self)
        line.pack(fill="x")
        for key, label, value, width in (("format", "帧格式", "Standard", 11),
                                         ("id", "ID (HEX)", "123", 11),
                                         ("dlc", "DLC", "4", 4),
                                         ("data", "DATA (HEX)", "11 22 33 44", 25)):
            self.input(line, key, label, value, width, ("Standard", "Extended") if key == "format" else ())
        ttk.Label(line, textvariable=self.decimal).pack(side="left", padx=3)
        self.form["id"].trace_add("write", self.show_decimal)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=6)
        self.input(actions, "filter", "接收过滤", "all", 11, ("all", "standard", "extended"))
        self.input(actions, "batch", "批量次数", "20", 6)
        self.single = ttk.Button(actions, text="发送单帧", command=lambda: self.submit(False))
        self.batch = ttk.Button(actions, text="批量发送", command=lambda: self.submit(True))
        for button in (self.single, self.batch):
            button.pack(side="left", padx=4)
        ttk.Button(actions, text="清空显示", command=self.clear).pack(side="left", padx=4)
        ttk.Label(self, textvariable=self.message, wraplength=780).pack(fill="x")
        ttk.Label(self, textvariable=self.totals).pack(fill="x", pady=(3, 4))

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        top, bottom = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(top, weight=2)
        panes.add(bottom, weight=3)
        self.transactions = tree(top, [("seq", "#", 48), ("time", "会话 +s", 68),
                                       ("dir", "方向", 60), ("format", "帧格式", 85),
                                       ("id", "ID HEX / DEC", 145), ("dlc", "DLC", 45),
                                       ("data", "DATA (HEX)", 154), ("ms", "往返 ms", 72),
                                       ("status", "结果", 99)], 6)
        self.transactions.bind("<<TreeviewSelect>>", self.select)
        self.details = tree(bottom, [("field", "字段", 170), ("tx", "CAN API TX", 210),
                                     ("rx", "CAN API RX", 210), ("match", "对照", 230)], 8)
        self.details.tag_configure("difference", background="#f9e5b8")
        self.set_active(False)
        self.update_totals()

    def input(self, parent, key, title, value, width, options=()):
        ttk.Label(parent, text=title).pack(side="left", padx=(0, 4))
        variable = tk.StringVar(value=value)
        self.form[key] = variable
        widget = (ttk.Combobox(parent, textvariable=variable, width=width, values=options, state="readonly")
                  if options else ttk.Entry(parent, textvariable=variable, width=width))
        widget.pack(side="left", padx=(0, 8))

    def show_decimal(self, *_):
        try:
            identifier = int(self.form["id"].get(), 16)
        except ValueError:
            self.decimal.set("DEC —")
        else:
            self.decimal.set(f"DEC {identifier}")

    def set_active(self, active):
        for button in (self.single, self.batch):
            button.configure(state="normal" if active else "disabled")

    def submit(self, batch):
        command = {key: self.form[key].get() for key in ("format", "id", "dlc", "data", "filter")}
        try:
            command["count"] = int(self.form["batch"].get(), 10) if batch else 1
            parse_request(command)
        except ValueError as error:
            self.message.set(f"INVALID · {error}")
            return
        self.message.set(f"正在等待 {command['count']} 笔 CAN API 结果…")
        self.send(command)

    def outcome(self, event):
        if "reason" in event:
            self.message.set(event["reason"])
        elif "counts" in event:
            self.message.set("本次发送完成 · " + " / ".join(f"{k} {v}" for k, v in event["counts"].items()))
        else:
            self.message.set("CAN 软件回环已连接，可发送帧。")

    def clear(self):
        self.rows.clear()
        self.transactions.delete(*self.transactions.get_children())
        self.details.delete(*self.details.get_children())

    def update_log(self, path):
        if path != self.path:
            self.path, self.offset, self.origin = path, 0, None
            self.counters.clear()
            self.update_totals()
            self.clear()
        if path is None or not path.is_file():
            return
        with path.open("rb") as log:
            log.seek(self.offset)
            while line := log.readline():
                if not line.endswith(b"\n"):
                    break
                self.offset = log.tell()
                self.add(json.loads(line))
        if self.rows and not self.transactions.selection():
            first = next(iter(self.rows))
            self.transactions.selection_set(first)

    def update_totals(self):
        c = self.counters
        self.totals.set(f"提交 {c['tx']} · 收到 {c['rx']} · 匹配 {c['matched']} · "
                        f"丢失 {c['lost']} · 过滤 {c['filtered']}")

    def add(self, row):
        sequence, tx, received = row["sequence"], row["tx"], row["rx"]
        iid = str(sequence)
        self.rows[iid] = row
        if self.origin is None:
            self.origin = row["monotonic_ns"]
        elapsed = (row["monotonic_ns"] - self.origin) / 1e9
        fields = tx or row["requested"] or {}
        identifier = fields.get("id")
        self.transactions.insert("", "end", iid=iid, values=(
            sequence, f"{elapsed:.3f}", "TX → RX" if tx and received else "TX" if tx else "—",
            ("Extended" if fields["ide"] else "Standard") if fields else "—",
            f"0x{identifier:X} / {identifier}" if identifier is not None else "—",
            fields.get("dlc", "—"), as_hex(fields.get("data", "")) or "—",
            f"{row['latency_ms']:.2f}" if row["latency_ms"] is not None else "—",
            row["status"]))
        self.transactions.see(iid)
        self.counters.update(tx=int(tx is not None), rx=len(received))
        self.counters["matched"] += int(row["matched"])
        self.counters["filtered"] += int(row["status"] == "FILTERED")
        self.counters["lost"] += int(tx is not None and not received and row["status"] == "TIMEOUT")
        self.update_totals()

    def select(self, _event=None):
        selected = self.transactions.selection()
        if not selected or selected[0] not in self.rows:
            return
        row = self.rows[selected[0]]
        tx = row["tx"] or {}
        rx = row["rx"][0] if row["rx"] else {}
        self.details.delete(*self.details.get_children())
        for label, key in (("帧格式 / IDE", "ide"), ("标识符", "id"), ("DLC", "dlc"), ("flags", "flags")):
            def value(fields):
                if key not in fields:
                    return "—"
                v = fields[key]
                if key == "ide":
                    return "Extended / 1" if v else "Standard / 0"
                return f"0x{v:X} / {v}" if key in ("id", "flags") else v
            self.detail_row(label, value(tx), value(rx))
        for i in range(max(tx.get("dlc", 0), rx.get("dlc", 0))):
            a, b = (frame.get("data", "")[2*i:2*i+2].upper() or "—" for frame in (tx, rx))
            self.detail_row(f"DATA[{i}]", a, b)
        self.details.insert("", "end", values=("接收过滤", row["filter"], rx.get("queue", "—"),
                                               "队列 1 标准；2 扩展"))
        self.details.insert("", "end", values=("结果", row["status"], f"{len(row['rx'])} 个 RX",
                                               row["error"] or ""))
        self.details.insert("", "end", values=("RTR", "未实现", "未实现", "当前只发送 Classical CAN 数据帧"))

    def detail_row(self, label, tx, rx):
        same = tx == rx and tx != "—"
        self.details.insert("", "end", values=(label, tx, rx, "一致" if same else "—" if rx == "—" else "不同"),
                            tags=("difference",) if rx != "—" and not same else ())
