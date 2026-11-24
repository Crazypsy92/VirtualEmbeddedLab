"""Tk workbench for the allowlisted embedded experiments."""
from datetime import datetime
import json
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk

from vel_env import ROOT, tool_environment, work
from vel_gui_features import BY_ID, CATEGORIES, FEATURES, capabilities, invocation
from vel_gui_results import output_summary

STATES = {"PASS": "通过", "COMPLETED": "会话结束", "FAIL": "失败", "CANCELLED": "已取消", "TIMEOUT": "超时",
          "BUSY": "工作区占用", "UNAVAILABLE": "依赖不可用"}


def report(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class Workbench:
    def __init__(self, window, advanced=None):
        self.window = window
        self.advanced = advanced
        self.detail_window = None
        self.detail_dashboard = None
        self.last_error = None
        self.window.title("VirtualEmbeddedLab · 仿真实验工作台")
        self.window.geometry("1080x720")
        self.window.minsize(900, 600)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.runs = work("gui-h1/runs")
        self.runs.mkdir(parents=True, exist_ok=True)
        self.feature = None
        self.job = self.folder = self.running_feature = None
        self.available = None
        self.closing = False
        self.live = False
        self.pending = False
        self.offset = 0
        self.partial = ""
        self.inbox = queue.SimpleQueue()
        self.category = tk.StringVar(value=CATEGORIES[0])
        self.mode = tk.StringVar()
        self.choice = tk.StringVar()
        self.status = tk.StringVar(value="正在检查后端依赖…")
        self.history = tk.StringVar()
        self.measurement = tk.StringVar()
        self.history_folder = None
        self.details = tk.StringVar()
        self.state = tk.StringVar(value="未运行")
        self.output = tk.StringVar(value="DO_0")
        self.input_mask = tk.StringVar(value="0")
        self.tail_key = None
        self.log_source = tk.StringVar(value="console.log")
        self.render()
        self.select(CATEGORIES[0])
        threading.Thread(target=self.check_dependencies, daemon=True).start()
        self.window.after(120, self.refresh)

    def check_dependencies(self):
        try:
            self.inbox.put(capabilities())
        except Exception as error:
            self.inbox.put(error)

    def render(self):
        self.window.configure(background="#132334")
        banner = tk.Frame(self.window, bg="#132334", padx=18, pady=12)
        banner.pack(fill="x")
        tk.Label(banner, text="VirtualEmbeddedLab", bg="#132334", fg="white",
                 font=("Sans", 20, "bold")).pack(side="left")
        tk.Label(banner, text="实验工作台", bg="#132334", fg="#80d9ca",
                 font=("Sans", 12)).pack(side="right")
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        nav = ttk.Frame(body, padding=(0, 0, 12, 0))
        nav.pack(side="left", fill="y")
        for name in CATEGORIES:
            ttk.Radiobutton(nav, text=name, variable=self.category, value=name,
                            command=lambda name=name: self.select(name)).pack(fill="x", pady=5)
        self.right = ttk.Frame(body)
        self.right.pack(side="right", fill="both", expand=True)
        toolbar = ttk.Frame(self.right)
        toolbar.pack(fill="x")
        self.title = ttk.Label(toolbar, font=("Sans", 16, "bold"))
        self.title.pack(side="left")
        self.stop = ttk.Button(toolbar, text="停止当前任务", command=self.cancel, state="disabled")
        self.stop.pack(side="right")
        ttk.Label(self.right, textvariable=self.status, wraplength=650).pack(anchor="w", pady=5)
        self.content = ttk.Frame(self.right)
        self.content.pack(fill="both", expand=True)

    def select(self, category):
        self.category.set(category)
        for widget in self.content.winfo_children():
            widget.destroy()
        self.feature = None
        self.start_button = None
        self.ops = []
        self.table = None
        self.log_box = None
        self.tail_key = None
        self.title.configure(text=category)
        if category == CATEGORIES[0]:
            ttk.Label(self.content, text="选择实验，运行并查看本次结果。", font=("Sans", 13)).pack(anchor="w", pady=10)
            self.overview = ttk.Label(self.content, text="正在检查可用后端…", wraplength=650)
            self.overview.pack(anchor="w", pady=8)
            for name in ("Modbus", "MCU / RTOS", "CAN", "FatFs"):
                ttk.Button(self.content, text=name, command=lambda n=name: self.select(n)).pack(anchor="w", pady=4)
            self.update_overview()
            return
        if category == CATEGORIES[-1]:
            self.render_logs()
            return
        entries = [x for x in FEATURES if x.category == category]
        self.choice.set(entries[0].title)
        combo = ttk.Combobox(self.content, textvariable=self.choice, state="readonly",
                             values=[x.title for x in entries], width=43)
        combo.pack(anchor="w", pady=(5, 8))
        combo.bind("<<ComboboxSelected>>", lambda _: self.render_feature(
            next(x for x in entries if x.title == self.choice.get())))
        self.panel = ttk.Frame(self.content)
        self.panel.pack(fill="both", expand=True)
        self.render_feature(entries[0])

    def update_overview(self):
        if self.available is None or self.category.get() != CATEGORIES[0]:
            return
        backends = ("qemu-system-arm", "Zephyr", "Renode cache", "ROS 2 demos")
        text = "   ·   ".join(f"{n}: {'可用' if self.available.get(n) else 'UNAVAILABLE'}" for n in backends)
        latest = next(iter(sorted(self.runs.glob("*/result.json"), key=lambda p: p.stat().st_mtime,
                                  reverse=True)), None)
        if latest:
            data = report(latest)
            name = BY_ID.get(data.get("id"))
            text += f"\n最近实验：{name.title if name else '—'} · {data.get('status', 'N/A')}"
        self.overview.configure(text=text + "\n物理硬件、RS485 电气特性：NOT TESTED")

    def render_feature(self, feature):
        self.feature = feature
        for widget in self.panel.winfo_children():
            widget.destroy()
        self.ops = []
        self.table = None
        ttk.Label(self.panel, text=feature.description, wraplength=650).pack(anchor="w")
        ttk.Label(self.panel, text=f"后端：{feature.backend}  ·  结果：{feature.evidence}",
                  wraplength=650).pack(anchor="w", pady=4)
        ttk.Label(self.panel, textvariable=self.details, wraplength=650).pack(anchor="w")
        bar = ttk.Frame(self.panel)
        bar.pack(fill="x", pady=7)
        modes = tuple(feature.modes)
        self.mode.set(modes[0] if modes else "不可执行")
        mode = ttk.Combobox(bar, textvariable=self.mode, values=modes, state="readonly", width=33)
        mode.pack(side="left")
        self.start_button = ttk.Button(bar, text="启动实验", command=self.start)
        self.start_button.pack(side="left", padx=7)
        ttk.Label(bar, textvariable=self.state).pack(side="left", padx=5)
        ttk.Label(self.panel, textvariable=self.history, wraplength=650).pack(anchor="w")
        ttk.Label(self.panel, textvariable=self.measurement, wraplength=650).pack(anchor="w", pady=(0, 3))
        if feature.id == "rtu":
            self.render_modbus(self.panel)
            if self.live and self.running_feature == "rtu" and hasattr(self, "last_snapshot"):
                self.present(self.last_snapshot)
        self.update_controls()

    def render_modbus(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Combobox(row, textvariable=self.output, values=[f"DO_{i}" for i in range(8)],
                     state="readonly", width=8).pack(side="left")
        buttons = [
            ("置 1", lambda: self.write_output(True)),
            ("置 0", lambda: self.write_output(False)),
            ("读取状态", lambda: self.send({"op": "read"})),
        ]
        for label, callback in buttons:
            widget = ttk.Button(row, text=label, command=callback)
            widget.pack(side="left", padx=3)
            self.ops.append(widget)
        ttk.Combobox(row, textvariable=self.input_mask, values=list(range(16)), state="readonly",
                     width=4).pack(side="left", padx=(8, 3))
        widget = ttk.Button(row, text="注入 DI 位图", command=self.inject_input)
        widget.pack(side="left")
        self.ops.append(widget)
        self.table = ttk.Treeview(parent, columns=("name", "value", "source"), show="headings", height=6)
        for key, title, width in [("name", "功能", 135), ("value", "读回值", 255), ("source", "实际来源", 195)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w")
        self.table.pack(fill="both", expand=True, pady=4)
        for key, name, origin in [("coils", "DO_0 … DO_7", "FC01 · 从站 GPIO 输出"),
                                  ("inputs", "DI_0 … DI_3", "FC02 · 从站 GPIO 输入"),
                                  ("holding", "Holding 0–7", "FC03"),
                                  ("registers", "Input 0–7", "FC04 · IR6/7 为 DI/DO 位图")]:
            self.table.insert("", "end", iid=key, values=(name, "N/A", origin))
        ttk.Label(parent, text="交互会话使用独立从站。启动后约 115 秒后自动结束，或可手动停止。",
                  wraplength=640).pack(anchor="w")

    def render_logs(self):
        bar = ttk.Frame(self.content)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="复制日志", command=self.copy_log).pack(side="left")
        if self.history_folder and not self.job:
            ttk.Button(bar, text="载入最近历史", command=self.load_history_log).pack(side="left", padx=4)
        ttk.Combobox(bar, textvariable=self.log_source, state="readonly", width=18,
                     values=("console.log", "rtu-wire.jsonl", "slave.log", "build.log", "result.json")).pack(side="left", padx=5)
        if self.advanced:
            ttk.Button(bar, text="打开寄存器与实时 RTOS 监控", command=self.open_advanced).pack(side="left", padx=5)
        self.log_path = ttk.Label(self.content, wraplength=650)
        self.log_path.pack(anchor="w")
        row = ttk.Frame(self.content)
        row.pack(fill="both", expand=True)
        self.log_box = tk.Text(row, wrap="word", font=("Monospace", 10), state="disabled")
        y = ttk.Scrollbar(row, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=y.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")

    def open_advanced(self):
        if self.detail_window and self.detail_window.winfo_exists():
            self.detail_window.lift()
            return
        self.detail_window = tk.Toplevel(self.window)
        self.detail_dashboard = self.advanced(self.detail_window)

    def load_history_log(self):
        if not self.job and self.history_folder:
            self.folder = self.history_folder
            self.tail_key = None

    def copy_log(self):
        if self.folder:
            self.window.clipboard_clear()
            path = self.folder / self.log_source.get()
            if path.is_file():
                self.window.clipboard_append(path.read_text(errors="replace"))

    def update_controls(self):
        if not self.feature:
            return
        feature = self.feature
        missing = [dep for dep in feature.dependencies if not (self.available or {}).get(dep)]
        executable = self.available is not None and not missing and bool(feature.modes)
        self.details.set("状态：正在探测" if self.available is None else
                         f"UNAVAILABLE · {feature.unavailable or '缺少 ' + ', '.join(missing)}" if not executable
                         else "可执行 · " + ("、".join(feature.dependencies) or "内置入口"))
        self.start_button.configure(state="normal" if executable and not self.job else "disabled")
        self.state.set("LIVE · 运行中" if self.job and self.running_feature == feature.id else "未运行 / 查看历史")
        if self.live and self.running_feature == feature.id:
            self.state.set("LIVE · 已连接")
        for widget in self.ops:
            widget.configure(state="normal" if self.live and not self.pending else "disabled")
        if getattr(self, "history_id", None) != feature.id:
            self.load_history(feature.id)

    def load_history(self, feature):
        records = []
        for path in self.runs.glob("*/result.json"):
            data = report(path)
            if data.get("id") == feature:
                records.append((data.get("finished", 0), data, path))
        if records:
            stamp, data, path = max(records, key=lambda item: item[0])
            self.history_folder = path.parent
            self.measurement.set("最近结果 · " + output_summary(feature, path.parent))
            self.history.set(f"HISTORY · {datetime.fromtimestamp(stamp):%m-%d %H:%M:%S} · "
                             f"{data['status']} · {path.parent.name}")
        else:
            self.history_folder = None
            self.measurement.set("")
            self.history.set("HISTORY · N/A")
        self.history_id = feature

    def start(self):
        if self.job or not self.feature:
            return
        try:
            invocation(self.feature.id, self.mode.get(), self.runs, self.available or {})
        except ValueError as error:
            self.status.set(str(error))
            return
        self.folder = folder = type(self.runs)(tempfile.mkdtemp(prefix=self.feature.id + "-", dir=self.runs))
        self.offset = 0
        self.partial = ""
        self.tail_key = None
        self.live = self.pending = False
        self.running_feature = self.feature.id
        self.last_error = None
        if self.table:
            for key in self.table.get_children():
                self.table.set(key, "value", "N/A")
        args = [sys.executable, ROOT / "scripts/vel_gui_job.py", self.feature.id, self.mode.get(), folder]
        try:
            with (folder / "console.log").open("w") as log:
                self.job = subprocess.Popen(args, cwd=ROOT, env=tool_environment(), stdin=subprocess.PIPE,
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            self.status.set(str(error))
            return
        self.status.set(f"正在启动 {self.feature.title} · 会话 {folder.name}")
        self.stop.configure(state="normal")
        self.update_controls()

    def cancel(self):
        if self.job and self.job.poll() is None:
            self.job.send_signal(signal.SIGTERM)
            self.status.set("正在停止并清理当前任务…")
            self.stop.configure(state="disabled")
            self.live = False
            self.update_controls()

    def close(self):
        self.closing = True
        if self.detail_window and self.detail_window.winfo_exists():
            self.detail_dashboard.close()
        if self.job:
            self.cancel()

    def write_output(self, state):
        choices = {f"DO_{index}": index for index in range(8)}
        if self.output.get() in choices:
            self.send({"op": "write", "index": choices[self.output.get()], "value": state})

    def inject_input(self):
        choices = {str(value): value for value in range(16)}
        if self.input_mask.get() in choices:
            self.send({"op": "input", "mask": choices[self.input_mask.get()]})

    def send(self, data):
        if not self.job or not self.live or self.pending:
            return
        try:
            self.job.stdin.write((json.dumps(data) + "\n").encode())
            self.job.stdin.flush()
            self.pending = True
            self.status.set("等待真实 Modbus 回读…")
        except OSError as error:
            self.status.set(str(error))
        self.update_controls()

    def present(self, event):
        for key in ("coils", "inputs", "holding", "registers"):
            values = event[key]
            self.table.set(key, "value", "  ".join(str(int(v)) for v in values))

    def events(self):
        path = self.folder / "console.log"
        with path.open("rb") as log:
            log.seek(self.offset)
            chunk = log.read(65536)
            self.offset = log.tell()
        text = self.partial + chunk.decode(errors="replace")
        *lines, self.partial = text.split("\n")
        for line in lines:
            if not line.startswith('{"event"'):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("event")
            if kind in ("ready", "result"):
                self.live = True
                if self.feature and self.feature.id == self.running_feature:
                    self.state.set("LIVE · 已连接")
                self.last_snapshot = event
                if self.table:
                    self.present(event)
                self.status.set("LIVE · FC05 已由 FC01 和 GPIO 位图确认" if
                                event.get("request", {}).get("op") == "write" else
                                "LIVE · 已读取实际 DO / DI / 寄存器")
            elif kind in ("operation_error", "session_error"):
                self.last_error = f"{kind} · {event.get('reason', 'N/A')}"
                self.status.set(self.last_error)
            if kind in ("ready", "result", "operation_error", "session_error"):
                self.pending = False

    def refresh(self):
        if not self.inbox.empty():
            value = self.inbox.get()
            self.available = value if isinstance(value, dict) else {}
            self.status.set("就绪" if isinstance(value, dict) else str(value))
            self.update_overview()
        if self.job:
            self.events()
            rc = self.job.poll()
            if rc is not None:
                data = report(self.folder / "result.json")
                status = data.get("status", "FAIL")
                self.status.set(f"{STATES.get(status, status)} · 退出码 {rc} · "
                                f"{data.get('reason') or self.last_error or self.folder.name} · 详见日志")
                self.job.stdin.close()
                self.job = None
                self.live = self.pending = False
                if self.table:
                    for key in self.table.get_children():
                        self.table.set(key, "value", "N/A（会话结束）")
                self.history_id = None
                self.stop.configure(state="disabled")
        if self.log_box and self.folder:
            p = self.folder / self.log_source.get()
            size = p.stat().st_size if p.is_file() else 0
            if self.tail_key != (p, size):
                content = "N/A · 本次没有该日志"
                if p.is_file():
                    with p.open("rb") as raw:
                        raw.seek(max(0, size - 28000))
                        content = raw.read(28000).decode(errors="replace")
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", "end")
                self.log_box.insert("1.0", content)
                self.log_box.configure(state="disabled")
                self.log_box.see("end")
                self.log_path.configure(text=str(p))
                self.tail_key = (p, size)
        if self.closing and not self.job and not (self.detail_window and self.detail_window.winfo_exists()):
            self.window.destroy()
            return
        self.update_controls()
        self.window.after(180, self.refresh)
