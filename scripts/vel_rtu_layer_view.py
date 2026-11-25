"""Layered ADU, UART and simulated direction views for one captured RTU transaction."""
import tkinter as tk
from tkinter import ttk

from vel_rtu_fault_rules import RULES
from vel_rtu_frames import decode
from vel_rtu_layers import BIT_US, CHAR_US, UART_LABELS, direction_event, host_events, uart_bits

COLORS = {"address": "#d5e9fa", "function": "#ece0fb", "data": "#d7eee6", "crc": "#f9e5b8"}
EVENT_LABELS = {"READY": "接收就绪 · 已绑定事务",
                "RX_DISPATCH": "从站将收到的帧交给 RTU 处理器",
                "RESPONSE_PREPARED": "响应已准备 · 等待 UART 发送",
                "GPIO": "仿真 GPIO 切换"}
FIELD_HELP = {"从站地址": "Unit ID", "功能码": "PDU 操作码", "CRC Lo": "校验低字节先上线路",
              "CRC Hi": "校验高字节", "起始地址": "16 位大端协议偏移",
              "地址": "16 位大端协议偏移", "数量": "16 位大端元素数量",
              "Byte Count": "后续数据字节数", "异常码": "从站返回的异常原因"}


def category(field):
    if field["offset"] == 0:
        return "address"
    if field["offset"] == 1:
        return "function"
    return "crc" if field["name"].startswith("CRC") else "data"


def describe(field, frame):
    name = field["name"]
    if name == "功能码" and frame.get("function_code", 0) & 128:
        return "异常功能码 · 原 FC | 0x80"
    if name == "异常码":
        return frame.get("error") or FIELD_HELP[name]
    return FIELD_HELP.get(name, "按功能码解释数据字段")


def spaced(hex_text):
    return " ".join(hex_text[i:i + 2] for i in range(0, len(hex_text), 2)).upper()


def rendered_value(value):
    if isinstance(value, list):
        return "  ".join(f"{bit['address']}={bit['value']}" for bit in value)
    return f"{value} / 0x{value:X}"


class LayerView:
    def __init__(self, parent, tree):
        self.raw = tk.StringVar()
        self.record = None
        self.log = None
        self.log_offset = 0
        self.events = {}
        self.field_bytes = {}
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.adu, self.uart, self.rs485, self.compare = [ttk.Frame(self.tabs) for _ in range(4)]
        for tab, title in zip((self.adu, self.uart, self.rs485, self.compare),
                              ("RTU ADU", "UART 8E1 模型", "RS-485 方向", "TX/RX 对照")):
            self.tabs.add(tab, text=title)
        raw_box = ttk.Frame(self.adu)
        raw_box.pack(fill="x", pady=(2, 3))
        self.hex_view = tk.Text(raw_box, height=2, wrap="none", font=("Monospace", 10), state="disabled")
        hscroll = ttk.Scrollbar(raw_box, orient="horizontal", command=self.hex_view.xview)
        self.hex_view.configure(xscrollcommand=hscroll.set)
        self.hex_view.pack(fill="x")
        hscroll.pack(fill="x")
        for key, color in COLORS.items():
            self.hex_view.tag_configure(key, background=color)
        self.hex_view.tag_configure("highlight", background="#285b86", foreground="white")
        self.detail = tree(self.adu, [("dir", "方向", 48), ("offset", "偏移", 48), ("length", "长度", 52),
                                     ("hex", "HEX", 91), ("field", "字段", 146), ("help", "说明", 200),
                                     ("value", "DEC / HEX", 185)], 8)
        for key, color in COLORS.items():
            self.detail.tag_configure(key, background=color)
        self.detail.bind("<<TreeviewSelect>>", self.select_field)
        ttk.Button(self.adu, text="查看所选字段的 UART 位", command=self.open_uart).pack(anchor="w")

        ttk.Label(self.uart, text=f"115200 baud · 8 数据位 · 偶校验 · 1 停止位 | 理论 {BIT_US:.2f} μs/bit，"
                                  f"{CHAR_US:.2f} μs/字符。固定教学模型，由采集字节推导；实际端口参数见传输配置。",
                  wraplength=800).pack(fill="x", pady=3)
        self.uart_rows = tree(self.uart, [("dir", "方向", 46), ("pos", "偏移", 47), ("byte", "HEX", 50),
                                        *((f"b{i}", label, 42) for i, label in enumerate(UART_LABELS)),
                                        ("field", "ADU 字段", 158)], 8)
        self.uart_rows.bind("<<TreeviewSelect>>", self.uart_selected)
        ttk.Button(self.uart, text="定位 ADU 字段", command=self.open_adu).pack(anchor="w")

        self.injection_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.injection_tab, text="注入证据")
        self.injection_note = tk.StringVar(value="选中故障事务可查看四处字节记录。")
        ttk.Label(self.injection_tab, textvariable=self.injection_note, wraplength=880).pack(fill="x", pady=4)
        self.injection = tree(self.injection_tab, [("stage", "链路边界", 190), ("hex", "HEX", 358),
                                                  ("crc", "CRC / 解码", 236)], 4)
        self.edits = tree(self.injection_tab, [("direction", "方向", 92), ("offset", "偏移", 62),
                                             ("old", "变更前", 110), ("new", "变更后", 110)], 4)
        self.edits.bind("<<TreeviewSelect>>", self.open_fault_byte)

        self.boundary = tk.StringVar()
        ttk.Label(self.rs485, textvariable=self.boundary, wraplength=820).pack(fill="x", pady=3)
        self.scope = tk.Canvas(self.rs485, height=71, highlightthickness=0, background="#f5f8fa")
        self.scope.pack(fill="x")
        self.scope.bind("<Configure>", lambda _: self.draw_gpio())
        self.timeline = tree(self.rs485, [("clock", "时间基准", 108), ("time", "相对 ms", 76),
                                         ("event", "已观测事件", 348),
                                         ("de", "DE", 45), ("re", "RE", 45)], 8)

        self.compare_note = tk.StringVar()
        ttk.Label(self.compare, textvariable=self.compare_note, wraplength=800).pack(fill="x", pady=3)
        self.comparison = tree(self.compare, [("pos", "偏移", 55), ("tx", "TX HEX", 72),
                                               ("tx_field", "TX 字段", 215), ("rx", "RX HEX", 72),
                                               ("rx_field", "RX 字段", 215)], 8)

    def set_log(self, path):
        if path != self.log:
            self.log, self.log_offset, self.events = path, 0, {}
        if path is None or not path.is_file():
            return
        updated = False
        with path.open("rb") as stream:
            stream.seek(self.log_offset)
            while line := stream.readline():
                if not line.endswith(b"\n"):
                    break
                self.log_offset = stream.tell()
                event = direction_event(line.decode(errors="replace"))
                if event:
                    sequence = event["sequence"]
                    self.events.setdefault(sequence, []).append(event)
                    updated |= self.record is not None and sequence == self.record["sequence"]
        if updated:
            self.render_direction()

    def present(self, record):
        self.record = record
        self.field_bytes.clear()
        self.raw.set("    ".join(f"{key.upper()}  {spaced(record[key]['raw_hex']) or '—'}"
                                  for key in ("tx", "rx")) if record else "")
        for table in (self.detail, self.uart_rows, self.timeline, self.comparison, self.injection, self.edits):
            table.delete(*table.get_children())
        self.hex_view.configure(state="normal")
        self.hex_view.delete("1.0", "end")
        self.compare_note.set("")
        self.injection_note.set("选中故障事务可查看四处字节记录。")
        if record is None:
            self.hex_view.configure(state="disabled")
            self.boundary.set("")
            self.scope.delete("all")
            return
        byte_rows = {}
        for line, key in enumerate(("tx", "rx"), 1):
            frame = record[key]
            prefix = key.upper()
            data = bytes.fromhex(frame["raw_hex"])
            by_offset = {}
            for field in frame["decoded_fields"]:
                offset, size = field["offset"], field["length"]
                kind = category(field)
                iid = f"{key}:{offset}"
                self.field_bytes[iid] = (line, offset, size, key)
                self.detail.insert("", "end", iid=iid, tags=(kind,), values=(
                    prefix, offset, size, field["raw_hex"].upper(), field["name"],
                    describe(field, frame), rendered_value(field["value"])))
                for pos in range(offset, offset + size):
                    by_offset[pos] = (iid, kind, field["name"])
            self.hex_view.insert("end", prefix + "  ")
            byte_rows[key] = []
            for pos, value in enumerate(data):
                field_id, kind, field_name = by_offset.get(pos, ("", "data", "未解析"))
                self.hex_view.insert("end", f"{value:02X}", (kind,))
                self.hex_view.insert("end", " ")
                self.uart_rows.insert("", "end", iid=f"{key}:{pos}", values=(
                    prefix, pos, f"{value:02X}", *uart_bits(value), field_name, field_id))
                byte_rows[key].append((f"{value:02X}", field_name))
            if not data:
                self.hex_view.insert("end", "—")
            if line == 1:
                self.hex_view.insert("end", "\n")
            if frame["crc_ok"] is not None:
                self.detail.insert("", "end", values=(prefix, "—", "—", "—", "CRC 校验", "帧值 / 计算值",
                    f"{'PASS' if frame['crc_ok'] else 'FAIL'} · 0x{frame['crc_received']:04X} / 0x{frame['crc_computed']:04X}"))
        self.hex_view.configure(state="disabled")
        for i in range(max(map(len, byte_rows.values()))):
            tx, rx = (byte_rows[key][i] if i < len(byte_rows[key]) else ("—", "—") for key in ("tx", "rx"))
            self.comparison.insert("", "end", values=(i, *tx, *rx))
        note = record.get("error") or "按从站地址、功能码与协议响应结构配对。"
        self.compare_note.set(f"#{record['sequence']} · {record['status']} · {note}")
        self.render_direction()
        if record.get("injection"):
            self.present_injection(record)
        elif record.get("recovery_of") is not None:
            self.injection_note.set(f"本笔为 #{record['recovery_of']} 注入后的 FC03 恢复验证。")

    def present_injection(self, record):
        audit = record["injection"]
        note = RULES[audit["rule"]].label + " · " + record["status"]
        if record["error"]:
            note += " · " + record["error"]
        self.injection_note.set(note)
        source = decode(bytes.fromhex(audit["original_tx_hex"]), True)
        raw = decode(bytes.fromhex(audit["slave_tx_hex"]), False, record["tx"])
        for label, frame in (("主站原始 TX", source), ("实际写入从站 PTY", record["tx"]),
                             ("从站原始响应（PTY）", raw), ("交给主站解析", record["rx"])):
            self.injection.insert("", "end", values=(label, spaced(frame["raw_hex"]) or "— 无字节",
                                  self.injection_crc(frame)))
        for key in ("tx", "rx"):
            for change in audit[f"{key}_changes"]:
                self.edits.insert("", "end", values=(key, change["offset"], change["before"] or "—",
                                                        change["after"] or "—"))

    @staticmethod
    def injection_crc(frame):
        if frame["crc_ok"] is None:
            return frame["status"] if frame["byte_length"] else "—"
        return (f"{'PASS' if frame['crc_ok'] else 'FAIL'} · "
                f"帧 0x{frame['crc_received']:04X} / 算 0x{frame['crc_computed']:04X}")

    def open_fault_byte(self, _event=None):
        selection = self.edits.selection()
        if not selection:
            return
        key, offset, *_ = self.edits.item(selection[0], "values")
        iid = f"{key}:{offset}"
        if self.uart_rows.exists(iid):
            self.uart_rows.selection_set(iid)
            self.uart_rows.see(iid)
            self.uart_selected()
            self.tabs.select(self.adu)

    def select_field(self, _event=None):
        selected = self.detail.selection()
        self.hex_view.tag_remove("highlight", "1.0", "end")
        if not selected or selected[0] not in self.field_bytes:
            return
        line, offset, size, _ = self.field_bytes[selected[0]]
        start = f"{line}.{4 + offset * 3}"
        end = f"{line}.{4 + (offset + size) * 3 - 1}"
        self.hex_view.tag_add("highlight", start, end)
        self.hex_view.see(start)

    def open_uart(self):
        selected = self.detail.selection()
        if selected and selected[0] in self.field_bytes:
            _, offset, _, key = self.field_bytes[selected[0]]
            iid = f"{key}:{offset}"
            self.uart_rows.selection_set(iid)
            self.uart_rows.see(iid)
            self.tabs.select(self.uart)

    def uart_selected(self, _event=None):
        selected = self.uart_rows.selection()
        if selected:
            iid = self.uart_rows.item(selected[0], "values")[-1]
            if self.detail.exists(iid) and iid:
                self.detail.selection_set(iid)
                self.detail.see(iid)
                self.select_field()

    def open_adu(self):
        self.uart_selected()
        self.tabs.select(self.adu)

    def render_direction(self):
        self.timeline.delete(*self.timeline.get_children())
        if not self.record:
            return
        seq = self.record["sequence"]
        events = self.events.get(seq, [])
        origin = events[0]["sim_ms"] if events else 0
        for label, elapsed in host_events(self.record):
            self.timeline.insert("", "end", values=("Host 单调钟", f"{elapsed:.3f}", label, "—", "—"))
        for event in events:
            label = EVENT_LABELS[event["kind"]]
            if event["kind"] == "GPIO":
                label += " · 发送" if event["de"] else " · 接收" if event["re"] else " · 切换中"
            self.timeline.insert("", "end", values=("Zephyr 仿真", event["sim_ms"] - origin,
                                                   label, event["de"], event["re"]))
        physical = self.record.get("transport", {}).get("scope") == "SERIAL_DEVICE"
        gap = "" if any(e["de"] for e in events) else " · 本笔未观测到从站发送使能"
        if physical:
            gap = " · 实际总线方向未采集"
        latency = self.record.get("latency_ms")
        timing = f" · TX→RX {latency:.2f} ms" if latency is not None else ""
        self.draw_gpio()
        self.boundary.set(f"#{seq} · {self.record['status']}{timing}{gap}｜各时钟独立，最后停止位完成时刻未测量")


    def draw_gpio(self):
        self.scope.delete("all")
        if not self.record:
            return
        events = self.events.get(self.record["sequence"], [])
        if not events:
            return
        start, end = events[0]["sim_ms"], events[-1]["sim_ms"]
        width = max(100, self.scope.winfo_width())
        span = max(1, len(events) - 1)
        for name, y, color in (("de", 30, "#306795"), ("re", 54, "#337c61")):
            self.scope.create_text(9, y, text=name.upper(), anchor="w", fill=color)
            previous = events[0][name]
            points = [36, y - previous * 9]
            for index, event in enumerate(events[1:], 1):
                x = 36 + (width - 56) * index / span
                current = event[name]
                points.extend((x, y - previous * 9, x, y - current * 9))
                previous = current
            if len(points) > 2:
                self.scope.create_line(*points, fill=color, width=2)
            else:
                self.scope.create_oval(34, y - previous * 9 - 2, 38, y - previous * 9 + 2, fill=color)
        self.scope.create_text(width - 8, 5, text=f"Zephyr 事件顺序 · 非等时比例 · 0…{end - start} ms", anchor="ne")
