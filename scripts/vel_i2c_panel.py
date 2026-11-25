"""I2C workbench with an event-driven field inspector and simulated waveform."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from vel_i2c import FAULTS, OPERATIONS, Request, decode, integer

LABELS = {"probe": "地址探测", "register-read": "寄存器读", "register-write": "寄存器写",
          "random-read": "EEPROM 随机读", "sequential-read": "EEPROM 顺序读", "page-write": "EEPROM 页写"}
PARTS = {"ADDRESS": "地址 + R/W", "POINTER": "寄存器指针", "DATA": "DATA",
         "START": "START", "RESTART": "Repeated START", "STOP": "STOP"}


class I2cPanel(ttk.Frame):
    def __init__(self, parent, tree, send):
        super().__init__(parent)
        self.send = send
        self.records = {}
        self.source = None
        self.offset = 0
        self.entries = {}
        self.connected = tk.StringVar(value="SIMULATED · 未连接")
        self.notice = tk.StringVar(value="启动仿真后可扫描地址或发送事务。")
        self.whole = tk.BooleanVar(value=True)
        ttk.Label(self, textvariable=self.connected).pack(anchor="w")
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=4)
        for idx, item in enumerate((
                ("khz", "速率 kHz", "100", 6, ("100", "400")),
                ("address", "7-bit HEX", "28", 7, ()),
                ("operation", "操作", LABELS["register-read"], 17, tuple(LABELS[op] for op in OPERATIONS)),
                ("offset", "偏移 HEX", "00", 6, ()),
                ("length", "读长度", "1", 5, ()),
                ("data", "DATA HEX", "12 34", 17, ()),
                ("fault", "故障", "none", 8, FAULTS),
                ("fault_byte", "写字节 #", "0", 5, ()),
                ("repeat", "批量次数", "10", 5, ()),
                ("gap", "批量间隔 µs", "5000", 6, ()))):
            self.input(controls, idx, *item)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.operations = []
        for label, action in (("扫描地址", self.scan), ("单次发送", lambda: self.submit(False)),
                              ("批量发送", lambda: self.submit(True)), ("推进仿真 5 ms", self.advance),
                              ("寄存器设备", lambda: self.select_device(False)),
                              ("EEPROM", lambda: self.select_device(True))):
            button = ttk.Button(bar, text=label, command=action)
            button.pack(side="left", padx=(0, 4))
            self.operations.append(button)
        self.send_button = self.operations[1]
        ttk.Button(bar, text="清空显示", command=self.clear).pack(side="left", padx=(0, 4))
        self.export_button = ttk.Button(bar, text="导出 JSONL", command=self.export, state="disabled")
        self.export_button.pack(side="left")
        ttk.Label(self, textvariable=self.notice, wraplength=940).pack(anchor="w", pady=3)

        self.history = tree(self, [("seq", "#", 44), ("operation", "事务", 150), ("address", "7-bit", 65),
                                   ("rate", "kHz", 57), ("result", "结果", 134),
                                   ("data", "读回 DATA", 165), ("reason", "故障位置 / 主机处理", 220)], 5)
        self.history.bind("<<TreeviewSelect>>", self.select)
        tabs = self.tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.bytes_tab = ttk.Frame(tabs)
        self.wave_tab = ttk.Frame(tabs)
        tabs.add(self.bytes_tab, text="字节 / 字段")
        tabs.add(self.wave_tab, text="SCL / SDA 时序")
        self.fields = tree(self.bytes_tab, [("part", "字段", 122), ("off", "线上偏移", 67),
                                           ("dir", "发送方", 77), ("val", "HEX", 48),
                                           ("bits", "前 8 位 · MSB → LSB", 140),
                                           ("ack", "第 9 位", 130), ("note", "地址与方向", 160)], 7)
        self.fields.bind("<<TreeviewSelect>>", lambda _: self.draw())
        ttk.Button(self.bytes_tab, text="查看时序", command=lambda: tabs.select(self.wave_tab)).pack(anchor="w")
        wave_bar = ttk.Frame(self.wave_tab)
        wave_bar.pack(fill="x")
        ttk.Checkbutton(wave_bar, text="完整事务（取消后查看选中字节）",
                        variable=self.whole, command=self.draw).pack(side="left")
        self.wave_label = tk.StringVar(value="SIMULATED")
        ttk.Label(wave_bar, textvariable=self.wave_label).pack(side="left", padx=8)
        self.canvas = tk.Canvas(self.wave_tab, background="#f6f8fb", height=154, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        scroll = ttk.Scrollbar(self.wave_tab, orient="horizontal", command=self.canvas.xview)
        scroll.pack(fill="x")
        self.canvas.configure(xscrollcommand=scroll.set)

    def input(self, parent, idx, key, title, value, width, choices):
        frame = ttk.Frame(parent)
        frame.grid(row=idx // 5, column=idx % 5, sticky="w", padx=(0, 7), pady=2)
        ttk.Label(frame, text=title).pack(side="left")
        var = self.entries[key] = tk.StringVar(value=value)
        if choices:
            widget = ttk.Combobox(frame, state="readonly", width=width, values=choices, textvariable=var)
        else:
            widget = ttk.Entry(frame, width=width, textvariable=var)
        widget.pack(side="left", padx=(3, 0))

    def select_device(self, eeprom):
        self.entries["address"].set(f"{self.addresses[eeprom]:02X}")
        self.entries["operation"].set(LABELS["random-read" if eeprom else "register-read"])

    def set_active(self, active, live):
        for button in self.operations:
            button.configure(state="normal" if active else "disabled")
        if not live:
            self.connected.set("SIMULATED · 未连接")

    def outcome(self, event):
        if event["event"] == "i2c_ready":
            self.connected.set(f"SIMULATED · {event['backend']} · 已连接")
            addresses = {row["model"]: row["address"] for row in event["devices"]}
            self.addresses = [addresses["register"], addresses["eeprom"]]
            self.entries["address"].set(f"{self.addresses[0]:02X}")
            self.notice.set("设备配置：" + "、".join(f"0x{row['address']:02X} {row['model']}" for row in event["devices"]))
        elif event["event"] == "i2c_result":
            if "found" in event:
                self.notice.set(f"扫描 {event['count']} 个地址 · ACK " + ("、".join(event["found"]) or "无")
                                + f" · NACK {event['status'].get('NACK', 0)}")
            elif last := event.get("last"):
                data = bytes.fromhex(last["data"]).hex(" ").upper()
                self.notice.set(f"{event['count']} 笔 · #{last['sequence']} {last['status']} "
                                + (last.get("reason") or data))
            else:
                self.notice.set(f"仿真时钟已推进到 {event['time_ns'] / 1000:.1f} µs")
        else:
            self.notice.set(event["reason"])

    def scan(self):
        self.send({"op": "scan", "khz": int(self.entries["khz"].get())})

    def advance(self):
        self.send({"op": "wait", "us": 5000})

    def submit(self, batch):
        v = {key: var.get().strip() for key, var in self.entries.items()}
        operation = next(key for key, label in LABELS.items() if label == v["operation"])
        try:
            request = Request(operation, int(v["address"], 16), int(v["khz"]), int(v["offset"], 16),
                              int(v["length"]) if operation.endswith("read") else 1,
                              v["data"] if operation.endswith("write") else "", v["fault"],
                              int(v["fault_byte"]) if v["fault"] in ("nack", "abort") else 0)
            repeat = integer(int(v["repeat"]), 1, 100, "批量次数") if batch else 1
            gap = integer(int(v["gap"]), 0, 25_000, "批量间隔 µs") if batch else 0
        except ValueError as error:
            self.notice.set(f"未发送 · {error}")
            return
        self.send({"op": "transfer", "request": request.__dict__, "repeat": repeat, "gap_us": gap})

    def clear(self):
        self.history.delete(*self.history.get_children())
        self.fields.delete(*self.fields.get_children())
        self.records.clear()
        self.current = None
        self.draw()

    def export(self):
        if self.source is None or not self.source.is_file():
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".jsonl",
                                           initialfile="i2c-transactions.jsonl",
                                           filetypes=[("JSON Lines", "*.jsonl")])
        if path:
            try:
                if Path(path).resolve() == self.source.resolve():
                    raise ValueError("请选择新的导出路径")
                # Copy only complete lines if a worker is currently appending.
                with self.source.open("rb") as source, Path(path).open("wb") as target:
                    for line in source:
                        if line.endswith(b"\n"):
                            target.write(line)
                self.notice.set(f"已导出 {path}")
            except (OSError, ValueError) as error:
                self.notice.set(f"导出失败 · {error}")

    def update_log(self, path):
        if self.source != path:
            self.source = path
            self.offset = 0
            self.clear()
        if path is None or not path.is_file():
            self.export_button.configure(state="disabled")
            return
        self.export_button.configure(state="normal")
        first = None
        with path.open("rb") as stream:
            stream.seek(self.offset)
            for _ in range(128):
                line = stream.readline()
                if not line.endswith(b"\n"):
                    break
                self.offset = stream.tell()
                row = json.loads(line)
                seq = str(row["sequence"])
                self.records[seq] = row
                req = row["request"]
                self.history.insert("", "end", iid=seq, values=(
                    seq, LABELS[req["operation"]], f"0x{req['address']:02X}", req["khz"], row["status"],
                    bytes.fromhex(row["data"]).hex(" ").upper(),
                    " · ".join(str(value) for value in (row["fault_at"], row["reason"], row["handling"])
                               if value is not None)))
                if first is None or row["status"] == "OK" or req["operation"] != "probe":
                    first = seq
        if first is not None and not self.history.selection():
            self.history.selection_set(first)
            self.history.see(first)
            self.select()

    def select(self, _event=None):
        selected = self.history.selection()
        if not selected:
            return
        self.current = self.records[selected[0]]
        self.fields.delete(*self.fields.get_children())
        for i, row in enumerate(decode(self.current["events"])):
            part = PARTS[row["kind"]]
            if "bits" not in row:
                self.fields.insert("", "end", iid=str(i), values=(part,))
                continue
            address = f"0x{row['address']:02X} · {row['direction']}={row['value'] & 1}" if "address" in row else ""
            sender = "主机" if row["sender"] == "controller" else "从机"
            owner = "主机" if row["ack_by"] == "controller" else "从机"
            ack = "ACK" if row["ack"] else "NACK"
            self.fields.insert("", "end", iid=str(i), values=(
                part, row["offset"], sender, f"{row['value']:02X}", " ".join(map(str, row["bits"][:8])),
                f"{owner} {ack} ({row['bits'][8]})", address))
        self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        row = getattr(self, "current", None)
        if not row:
            self.wave_label.set("SIMULATED")
            return
        events = row["events"]
        period = row["period_ns"]
        selection = self.fields.selection()
        if selection and not self.whole.get():
            events = [events[int(selection[0])]]
        start = events[0]["start_ns"] if events else row["start_ns"]
        end = events[-1]["end_ns"] if events else row["end_ns"]
        duration = max(period, end - start)
        bit_pixels = max(30 if len(events) <= 1 else 18, (canvas.winfo_width() - 70) * period / duration)
        scale = bit_pixels / period
        self.wave_label.set(f"SIMULATED · {row['request']['khz']} kHz · SCL 周期 {period / 1000:g} µs · #{row['sequence']}")
        canvas.configure(scrollregion=(0, 0, 75 + duration * scale, 140))
        canvas.xview_moveto(0)

        def x(ns):
            return 55 + (ns - start) * scale

        for key, top, color in (("scl", 48, "#15528a"), ("sda", 99, "#245d41")):
            canvas.create_text(13, top + 9, text=key.upper(), anchor="w", fill=color)
            previous = 1
            last = start
            for sample in row["edges"]:
                ns = sample["ns"]
                if ns < start:
                    previous = sample[key]
                    continue
                if ns >= end:
                    break
                next_level = sample[key]
                level = top + 20 * (1 - previous)
                canvas.create_line(x(last), level, x(ns), level, fill=color, width=2)
                canvas.create_line(x(ns), level, x(ns), top + 20 * (1 - next_level), fill=color, width=2)
                last, previous = ns, next_level
            canvas.create_line(x(last), top + 20 * (1 - previous), x(end), top + 20 * (1 - previous),
                               fill=color, width=2)
        for field in decode(events):
            left = field["start_ns"]
            if "bits" not in field:
                edge = x(field["edge_ns"])
                canvas.create_line(edge, 26, edge, 122, fill="#a34f19", dash=(3, 2))
                canvas.create_text(edge, 3, text=PARTS[field["kind"]],
                                   anchor="ne" if field["kind"] == "STOP" else "nw", fill="#833e13")
                continue
            title = PARTS[field["kind"]]
            if field["kind"] == "ADDRESS":
                title = f"0x{field['address']:02X} · {field['direction']}"
            canvas.create_text(x(left), 16, text=f"{title}  {field['value']:02X}", anchor="nw", fill="#14283a")
            names = (["A6", "A5", "A4", "A3", "A2", "A1", "A0", "R/W"] if field["kind"] == "ADDRESS"
                     else [f"D{index}" for index in range(7, -1, -1)])
            for i, name in enumerate([*names, "9"]):
                point = x(left + i * period)
                color = "#a34f19" if i == 8 else "#91a2b4"
                canvas.create_line(point, 34, point, 124, fill=color, dash=(2, 3))
                text = name
                if i == 8:
                    if bit_pixels >= 40:
                        text = "9 ACK" if field["ack"] else "9 NACK"
                    else:
                        text = "✓9" if field["ack"] else "×9"
                canvas.create_text(point + bit_pixels / 2, 133, text=text, fill="#14283a",
                                   font=("Sans", 8 if bit_pixels < 30 else 10))
