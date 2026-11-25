"""Tk controls and transaction history for the RTU workbench tab."""
import json
import tkinter as tk
from tkinter import ttk

from vel_rtu_frames import FC_NAMES
from vel_rtu_fault_panel import FaultControls
from vel_rtu_layer_view import LayerView


class ProtocolPanel(ttk.Frame):
    def __init__(self, parent, send):
        super().__init__(parent, padding=(5, 5))
        self.send = send
        self.inputs = {}
        self.rows = {}
        self.path = None
        self.result_time = None
        self.offset = 0
        self.fault_selection = None
        self.choice = tk.StringVar()
        self.message = tk.StringVar(value="启动交互会话后可发送请求。")
        options = ttk.Frame(self)
        options.pack(fill="x")
        self.functions = {f"{code:02X}  {name}": code for code, name in FC_NAMES.items()}
        chooser = ttk.Combobox(options, textvariable=self.choice, values=tuple(self.functions),
                               width=21, state="readonly")
        chooser.pack(side="left", padx=(0, 8))
        chooser.current(0)
        chooser.bind("<<ComboboxSelected>>", self.change)
        for key, title, default, width in (("unit", "从站", "1", 4), ("address", "地址", "0", 5),
                                          ("argument", "数量", "8", 16)):
            group = ttk.Frame(options)
            group.pack(side="left", padx=(0, 8))
            label = ttk.Label(group, text=title)
            label.pack(side="left", padx=(0, 3))
            value = tk.StringVar(value=default)
            ttk.Entry(group, textvariable=value, width=width).pack(side="left")
            self.inputs[key] = (label, value)
        self.send_button = ttk.Button(options, text="发送", command=self.submit, state="disabled")
        self.send_button.pack(side="left")
        ttk.Button(options, text="清空显示", command=self.clear).pack(side="left", padx=5)
        ttk.Label(self, textvariable=self.message, wraplength=840).pack(fill="x", pady=4)

        self.faults = FaultControls(self, send, self.clear_faults)
        self.faults.pack(fill="x", pady=(0, 3))

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        top = ttk.Frame(panes)
        bottom = ttk.Frame(panes)
        panes.add(top, weight=2)
        panes.add(bottom, weight=3)
        self.list = self.tree(top, [("seq", "#", 42), ("time", "会话 +s", 75), ("function", "功能 / 地址", 92),
                                    ("direction", "方向", 64), ("bytes", "TX/RX 字节", 86),
                                    ("crc", "CRC TX/RX", 88), ("matched", "配对", 49),
                                    ("ms", "耗时 ms", 70), ("status", "结果", 108),
                                    ("purpose", "用途", 108)], 5)
        self.list.bind("<<TreeviewSelect>>", self.show_selected)
        self.layers = LayerView(bottom, self.tree)
        self.raw = self.layers.raw
        self.detail = self.layers.detail

    @staticmethod
    def tree(parent, columns, height):
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        tree = ttk.Treeview(box, columns=[key for key, *_ in columns], show="headings", height=height)
        scroll = ttk.Scrollbar(box, command=tree.yview)
        horizontal = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=width, anchor="w")
        return tree

    def change(self, _event=None):
        fc = self.functions[self.choice.get()]
        label, argument = self.inputs["argument"]
        label.configure(text="数量" if fc <= 4 else "值（逗号分隔）" if fc in (15, 16) else "写入值")
        argument.set({1: "8", 2: "4", 3: "8", 4: "8", 5: "1", 6: "1",
                      15: "1,0,1,0,0,0,0,0", 16: "1,10,500"}.get(fc))

    @staticmethod
    def number(text):
        text = text.strip()
        return int(text, 16 if text.lower().startswith("0x") else 10)

    def submit(self):
        try:
            fc = self.functions[self.choice.get()]
            command = {"op": "protocol", "fc": fc, "unit": self.number(self.inputs["unit"][1].get()),
                       "address": self.number(self.inputs["address"][1].get())}
            argument = self.inputs["argument"][1].get()
            if fc <= 4:
                command["count"] = self.number(argument)
            else:
                command["values"] = [self.number(token) for token in argument.split(",")]
        except ValueError:
            self.message.set("填写十进制整数或 0x 十六进制值。多个值用逗号分隔。")
            return
        self.message.set("正在等待实际串口响应…")
        self.send(command)

    def set_active(self, active, *, simulation=True):
        self.faults.enable(active and simulation)
        self.send_button.configure(state="normal" if active and not self.faults.running else "disabled")

    def outcome(self, event):
        if event["event"] == "fault_result":
            self.faults.outcome(event)
            self.fault_selection = str(event["sequence"])
            return
        if "reason" in event:
            if self.faults.running:
                self.faults.cancel(report=False)
                self.faults.status.set(event["reason"])
            self.message.set(event["reason"])
            return
        label = "写入及回读通过" if event["verified"] else "读取通过"
        bitmap = f" · DO 位图 0x{event['do_bitmap']:02X}" if "do_bitmap" in event else ""
        self.message.set(f"{label} · {event['values']}{bitmap}")

    def clear(self):
        self.rows.clear()
        self.list.delete(*self.list.get_children())
        self.fault_selection = None
        self.layers.present(None)

    def clear_faults(self):
        selected = set(self.list.selection())
        ids = [key for key, row in self.rows.items() if "injection" in row or "recovery_of" in row]
        for key in ids:
            del self.rows[key]
            self.list.delete(key)
        if selected.intersection(ids):
            self.layers.present(None)

    def update_log(self, path):
        if path != self.path:
            self.path, self.offset, self.result_time = path, 0, None
            self.clear()
        self.layers.set_log(path.with_name("slave.log") if path else None)
        if path is None or not path.is_file():
            return
        with path.open("rb") as log:
            log.seek(self.offset)
            while line := log.readline():
                if not line.endswith(b"\n"):
                    break
                self.offset = log.tell()
                self.add(json.loads(line))
        if self.fault_selection and self.list.exists(self.fault_selection):
            self.list.selection_set(self.fault_selection)
            self.list.see(self.fault_selection)
            self.fault_selection = None
            self.layers.tabs.select(self.layers.injection_tab)
        if self.rows and not self.list.selection():
            first = next(iter(self.rows))
            self.list.selection_set(first)

    @staticmethod
    def crc_label(value):
        return "—" if value is None else "PASS" if value else "FAIL"

    def add(self, record):
        tx, rx = record["tx"], record["rx"]
        sequence = str(record["sequence"])
        self.rows[sequence] = record
        if self.result_time is None:
            self.result_time = record["monotonic_ns"]
        timestamp = (record["monotonic_ns"] - self.result_time) / 1e9
        function = "—" if tx["function_code"] is None else f"{tx['function_code']:02X} / {tx.get('address', '—')}"
        elapsed = record["latency_ms"]
        self.list.insert("", "end", iid=sequence, values=(
            sequence, f"{timestamp:.3f}", function, "TX → RX", f"{tx['byte_length']} / {rx['byte_length']}",
            f"{self.crc_label(tx['crc_ok'])}/{self.crc_label(rx['crc_ok'])}", "是" if record["matched"] else "否",
            f"{elapsed:.2f}" if elapsed is not None else "—", record["status"], record["purpose"]))
        self.list.see(sequence)

    def show_selected(self, _event=None):
        selected = self.list.selection()
        if selected and selected[0] in self.rows:
            self.layers.present(self.rows[selected[0]])
