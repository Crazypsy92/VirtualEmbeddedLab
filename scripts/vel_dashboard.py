#!/usr/bin/env python3
"""VirtualEmbeddedLab's local WSLg console. Values come from actual run logs."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

from vel_env import ROOT, tool_environment, work
from vel_jobs import lock_status
from vel_inspector import snapshot

BG = "#101926"
PANEL = "#182538"
INK = "#e8eff8"
MUTED = "#a8b8cc"
ACCENT = "#55d7bc"

SOURCES = {
    "Cortex-M3": ("build/*arm*/qemu_functional.log", "build/evidence/arm/qemu_functional.log",
                  "build/console/*/arm.log", "evidence/stage1/qemu_functional.log"),
    "FreeRTOS": ("build/*/stage3_1/scheduler.log", "build/evidence/freertos/stage3_1/scheduler.log",
                 "build/console/*/freertos.log", "evidence/stage3/stage3_1/scheduler.log"),
    "Zephyr": ("build/*/stage4_1/kernel.log", "build/evidence/zephyr/stage4_1/kernel.log",
                "build/console/*/stage4_1/kernel.log", "build/console/*/zephyr.log", "evidence/stage4/stage4_1/kernel.log"),
    "Zephyr 虚拟传感器": ("build/*/stage4_2/sensor.log",
                       "build/evidence/zephyr/stage4_2/sensor.log", "build/console/*/stage4_2/sensor.log"),
}
METRICS = {
    "Cortex-M3": {"Tick 起始": "first", "Tick 最终": "final", "SVC 次数": "svc",
                  "PendSV 次数": "pendsv", "UART": "uart", "异常检查失败数": "failures"},
    "FreeRTOS": {"Tick 计数": "ticks", "任务切换": "switches", "抢占验证": "preemption",
                 "任务 A 执行次数": "worker_a", "任务 B 执行次数": "worker_b",
                 "可用堆（字节）": "heap_free", "最小可用堆（字节）": "heap_min",
                 "任务 A 栈余量（字）": "stack_a", "任务 B 栈余量（字）": "stack_b"},
    "Zephyr": {"内核运行时间（ms）": "uptime", "定时器触发": "timer", "工作队列执行": "work",
                "任务 A 执行次数": "worker_a", "任务 B 执行次数": "worker_b",
                "抢占验证": "preemption"},
    "Zephyr 虚拟传感器": {"采样数": "samples", "并发采样数": "concurrent",
                       "不可用传感器验证": "unavailable"},
    "GPIO native_sim": {"模拟输出引脚": "gpio_outputs", "模拟输入引脚": "gpio_inputs",
                         "输出翻转": "gpio_toggles", "输入边沿": "input_edges",
                         "UART 帧数": "uart_frames"},
    "Modbus 网关": {"收到 TCP 请求": "received", "已发响应": "sent", "RTU 超时": "timeouts",
                  "异常响应": "exceptions", "TCP 连接": "connections",
                  "RTU 等待队列": "queued", "完成队列": "completed", "RTU 处理中": "active"},
}


def tail(path, limit=64000):
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - limit))
            return stream.read(limit).decode(errors="replace")
    except OSError:
        return ""


def latest(candidates, marker):
    files = []
    for path in candidates:
        try:
            files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    for stamp, path in sorted(files, reverse=True):
        content = tail(path)
        if marker in content:
            return stamp, path, content
    return None


def read_sample(name):
    if name == "GPIO native_sim":
        files = list(ROOT.glob("build/*/native_sim/acceptance.json"))
        files.append(ROOT / "evidence/stage8_1/native_sim/acceptance.json")
        if configured := os.environ.get("VEL_STAGE8_1_EVIDENCE"):
            files.append(Path(configured) / "native_sim/acceptance.json")
        sample = latest(files, "gpio_toggles")
        if sample:
            stamp, path, content = sample
            try:
                return json.loads(content), stamp, path
            except ValueError:
                pass
        return {}, None, None
    if name == "Modbus 网关":
        candidates = list(work("gateway_stage8_3_ws").glob("runs/*/gateway*.log"))
        candidates += list(work("gateway_stage8_3_1_ws").glob("runs/*/gateway*.log"))
        candidates += list(ROOT.glob("build/final-recheck/gateway_stage8_3_1_ws/runs/*/gateway*.log"))
        sample = latest(candidates, "GW_STATS ")
    else:
        files = {path for pattern in SOURCES[name] for path in ROOT.glob(pattern)}
        sample = latest(files, "[TICK]" if name == "Cortex-M3" else "[STAT]")
    if sample is None:
        return {}, None, None
    stamp, path, content = sample
    if name == "Modbus 网关":
        summaries = [line for line in content.splitlines() if line.startswith("GW_STATS ")]
        values = dict(re.findall(r"(\w+)=(\d+)", summaries[-1])) if summaries else {}
    else:
        values = dict(re.findall(r"\[STAT\] (\w+)=(-?\d+)", content))
        for key, expression in {
            "first": r"\[TICK\] first=(\d+)", "final": r"\[TICK\] final=(\d+)",
            "svc": r"\[SVC\] count=(\d+)", "pendsv": r"\[PENDSV\] count=(\d+)",
            "uart": r"\[UART\] (PASS|FAIL)", "failures": r"\[EXCEPTION\] failures=(\d+)",
        }.items():
            if match := re.search(expression, content):
                values[key] = match[1]
    return values, stamp, path


VIEWS = (
    ("内核", ("Cortex-M3", "Zephyr")),
    ("外设", ("Zephyr 虚拟传感器", "GPIO native_sim", "Modbus 网关")),
    ("RTOS", ("FreeRTOS",)),
)


# Register names follow the MPS2 AN385 models in QEMU 8.2.2.
PERIPHERALS = (
    ("UART0", "0x40004000", "实时采样 / 命令串口",
     (("CTRL", "uart_ctrl"), ("STATE", "uart_state"), ("BAUDDIV", "uart_div"))),
    ("UART1–4", "0x40005000、0x40006000、0x40007000、0x40009000", "已建模，未采样", ()),
    ("APB Timer 0", "0x40000000", "实时采样",
     (("CTRL", "timer_ctrl"), ("VALUE", "timer_value"), ("RELOAD", "timer_reload"))),
    ("APB Timer 1", "0x40001000", "已建模，未采样", ()),
    ("双定时器", "0x40002000", "已建模，未采样", ()),
    ("Watchdog", "0x40008000", "已建模，未采样", ()),
    ("SPI / PL022", "0x40020000、0x40021000、0x40026000、0x40027000", "已建模，未采样", ()),
    ("I²C", "0x40022000、0x40023000、0x40029000、0x4002A000", "已建模，未采样", ()),
    ("GPIO 0–3", "0x40010000–0x40013000", "AN385 为占位；虚拟 GPIO 另见历史测试", ()),
    ("外接 ADC 接口", "0x40025000", "仅 PL022 控制器，未接 ADC 模型", ()),
    ("DMA / I²S", "—", "无可用采样；I²S 为占位", ()),
)
CORE = (("SCB", "CPUID", "cpuid"), ("SCB", "ICSR", "icsr"), ("SCB", "VTOR", "vtor"),
        ("SysTick", "LOAD", "systick_load"), ("SysTick", "VAL", "systick_value"),
        ("NVIC", "ISER0", "nvic_enabled"), ("NVIC", "ISPR0", "nvic_pending"))
TASK_STATES = {0: "运行", 1: "就绪", 2: "阻塞", 3: "挂起", 4: "删除"}


class Dashboard:
    def __init__(self, window):
        self.window = window
        self.window.title("VirtualEmbeddedLab · 实验控制台")
        self.window.geometry("1050x720")
        self.window.minsize(810, 540)
        self.window.configure(background=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.job = self.log = self.job_name = None
        self.stop_at = None
        self.closing = False
        self.last_log = None
        self.inspector_log = None
        self.command_pending = None
        self.sample_paths = {}
        self.buttons = []
        self.status = tk.StringVar(value="就绪 · 可查看已有采样，或启动一次新测试")
        self.lock_text = tk.StringVar()
        self.log_choice = tk.StringVar(value="本次任务")
        self.style()
        self.render()
        self.refresh()

    def style(self):
        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(".", font=("Sans", 11), background=BG, foreground=INK)
        style.configure("TButton", background=PANEL, foreground=INK, padding=(12, 7))
        style.map("TButton", background=[("active", "#263b52")],
                  foreground=[("disabled", MUTED)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(19, 8))
        style.map("TNotebook.Tab", background=[("selected", "#263b52")],
                  foreground=[("selected", ACCENT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=INK, borderwidth=0, rowheight=27)
        style.configure("Treeview.Heading", background="#263b52", foreground=INK,
                        font=("Sans", 10, "bold"))
        style.map("Treeview", background=[("selected", "#314e67")])
        style.configure("Title.TLabel", font=("Sans", 25, "bold"), foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Status.TLabel", foreground=ACCENT)

    def render(self):
        frame = ttk.Frame(self.window, padding=(22, 16))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="VirtualEmbeddedLab", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="虚拟嵌入式实验控制台  /  QEMU · Zephyr · FreeRTOS · Modbus",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 12))
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 10))
        for label, action in [("启动实时监控", "inspector"), ("Cortex-M3 测试", "arm"),
                              ("Zephyr 测试", "zephyr"), ("FreeRTOS 测试", "freertos"),
                              ("外设测试", "sensor"), ("网关验收", "gateway")]:
            button = ttk.Button(bar, text=label, command=lambda name=action: self.start(name))
            button.pack(side="left", padx=(0, 5))
            self.buttons.append(button)
        self.stop_button = ttk.Button(bar, text="停止本次任务", command=self.cancel, state="disabled")
        self.stop_button.pack(side="right")
        ttk.Label(frame, textvariable=self.status, style="Status.TLabel").pack(anchor="w")
        ttk.Label(frame, textvariable=self.lock_text, style="Muted.TLabel").pack(anchor="w", pady=(3, 10))
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill="both", expand=True)
        self.tables = {}
        self.render_inspector()
        for title, sources in VIEWS:
            view = ttk.Frame(self.tabs, padding=12)
            self.tabs.add(view, text=title + " · 历史")
            ttk.Label(view, text="以下为模拟器输出的最近样本。空值表示该样本未提供此项。",
                      style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
            table = ttk.Treeview(view, columns=("module", "name", "value"), show="headings")
            for key, label, width in [("module", "目标 / 来源", 220), ("name", "指标", 290),
                                      ("value", "最近样本", 260)]:
                table.heading(key, text=label)
                table.column(key, width=width, stretch=key != "module", anchor="w")
            scrollbar = ttk.Scrollbar(view, orient="vertical", command=table.yview)
            table.configure(yscrollcommand=scrollbar.set)
            table.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            for name in sources:
                table.insert("", "end", iid=name+":source", values=(name, "采样时间", "暂无"))
                for label, key in METRICS[name].items():
                    table.insert("", "end", iid=name+":"+key, values=(name, label, "—"))
            self.tables[table] = sources
        view = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(view, text="日志")
        select = ttk.Combobox(view, textvariable=self.log_choice, state="readonly",
                              values=("本次任务", *METRICS), width=28)
        select.pack(anchor="w")
        self.log_path = ttk.Label(view, text="暂无日志", style="Muted.TLabel")
        self.log_path.pack(anchor="w", pady=6)
        self.log_box = tk.Text(view, wrap="word", background="#0b1320", foreground=INK,
                               insertbackground=INK, borderwidth=0, padx=12, pady=9,
                               font=("Monospace", 10), state="disabled")
        scroll = ttk.Scrollbar(view, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def grid_table(self, parent, columns, height=9):
        table = ttk.Treeview(parent, columns=[key for key, _, _ in columns],
                             show="headings", height=height)
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")
        return table

    def render_inspector(self):
        core = ttk.Frame(self.tabs, padding=12)
        peripherals = ttk.Frame(self.tabs, padding=12)
        tasks = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(core, text="内核寄存器")
        self.tabs.add(peripherals, text="片上外设")
        self.tabs.add(tasks, text="RTOS 任务")
        self.live_text = tk.StringVar(value="等待实时监控 · QEMU MPS2 AN385")
        for view in (core, peripherals, tasks):
            ttk.Label(view, textvariable=self.live_text, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self.core_table = self.grid_table(core, (("block", "模块", 150),
                                                ("register", "寄存器", 150), ("value", "值", 210)))
        self.core_table.pack(fill="both", expand=True)
        for block, label, key in CORE:
            self.core_table.insert("", "end", iid=key, values=(block, label, "—"))
        self.peripheral_table = self.grid_table(peripherals, (("device", "片上模块", 150),
                                                             ("address", "基地址", 400),
                                                             ("support", "本目标支持状态", 320)), 11)
        self.peripheral_table.pack(fill="both", expand=True)
        for name, address, support, _ in PERIPHERALS:
            self.peripheral_table.insert("", "end", iid=name, values=(name, address, support))
        self.register_text = tk.StringVar(value="选择外设查看寄存器与当前值")
        ttk.Label(peripherals, textvariable=self.register_text, style="Status.TLabel").pack(anchor="w", pady=10)
        self.peripheral_table.selection_set("UART0")
        self.peripheral_table.bind("<<TreeviewSelect>>", lambda _: self.show_peripheral())
        self.live_values = {}
        bar = ttk.Frame(tasks)
        bar.pack(fill="x", pady=(0, 8))
        self.task_summary = tk.StringVar(value="等待 FreeRTOS 快照")
        ttk.Label(bar, textvariable=self.task_summary).pack(side="left")
        self.pause_worker = ttk.Button(bar, text="挂起 Producer", command=lambda: self.send_worker(b"p"))
        self.resume_worker = ttk.Button(bar, text="恢复 Producer", command=lambda: self.send_worker(b"r"))
        for button in (self.resume_worker, self.pause_worker):
            button.pack(side="right", padx=3)
            button.configure(state="disabled")
        self.task_table = self.grid_table(tasks, (("id", "ID", 70), ("task", "任务", 180),
                                                 ("state", "调度状态", 120), ("priority", "优先级", 90),
                                                 ("stack", "最小栈余量（字）", 180)), 8)
        self.task_table.pack(fill="both", expand=True)
        ttk.Label(tasks, text="操作仅作用于实时演示固件的 Producer；任务状态由 FreeRTOS 返回。",
                  style="Muted.TLabel").pack(anchor="w", pady=8)

    def show_peripheral(self):
        selected = self.peripheral_table.selection()
        if not selected:
            return
        name, _, support, registers = next(item for item in PERIPHERALS if item[0] == selected[0])
        values = [f"{label}  0x{self.live_values[key]:08X}" if key in self.live_values else f"{label}  —"
                  for label, key in registers]
        self.register_text.set(f"{name}   " + ("    |    ".join(values) if values else support))

    def send_worker(self, command):
        if not self.job or self.job_name != "inspector" or self.job.poll() is not None:
            return
        if not self.live_values or self.command_pending:
            return
        try:
            self.job.stdin.write(command)
            self.job.stdin.flush()
            self.command_pending = (self.live_values.get("commands", 0), time.monotonic() + 3)
        except OSError:
            self.status.set("命令发送失败，实时监控已结束。")

    def refresh_inspector(self):
        live = bool(self.job and self.job_name == "inspector" and not self.stop_at)
        values, tasks = snapshot(tail(self.inspector_log)) if self.inspector_log else ({}, [])
        stamp = None
        if values and self.inspector_log:
            try:
                stamp = self.inspector_log.stat().st_mtime
            except OSError:
                pass
        fresh = bool(live and stamp and time.time() - stamp < 2)
        if stamp:
            when = datetime.fromtimestamp(stamp).strftime("%H:%M:%S")
            self.live_text.set(f"QEMU MPS2 AN385  ·  {'实时采样' if fresh else '最近快照'}  ·  {when}")
        elif live:
            self.live_text.set("QEMU MPS2 AN385  ·  等待构建或首个采样")
        self.live_values = values
        for _, _, key in CORE:
            self.core_table.set(key, "value", f"0x{values[key]:08X}" if key in values else "—")
        self.show_peripheral()
        if values:
            self.task_summary.set(f"Tick {values['tick']}   ·   切换 {values.get('switches', '—')}   ·   "
                                  f"队列 {values.get('queue', '—')}/4   ·   空闲堆 {values.get('heap', '—')} B")
        current = set()
        producer_state = None
        for name, task in sorted(tasks, key=lambda item: item[1]["id"]):
            ident = str(task["id"])
            current.add(ident)
            if name == "Producer":
                producer_state = task["state"]
            row = (ident, name, TASK_STATES.get(task["state"], "未知"), task["priority"], task["stack_words"])
            if self.task_table.exists(ident):
                self.task_table.item(ident, values=row)
            else:
                self.task_table.insert("", "end", iid=ident, values=row)
        for ident in set(self.task_table.get_children()) - current:
            self.task_table.delete(ident)
        if self.command_pending:
            before, until = self.command_pending
            if values.get("commands", 0) > before:
                self.status.set("实时监控运行中 · 已收到固件确认")
                self.command_pending = None
            elif time.monotonic() > until or not live:
                self.command_pending = None
                if live:
                    self.status.set("实时监控运行中 · 等待固件确认超时")
        ready = fresh and not self.command_pending and producer_state is not None
        self.pause_worker.configure(state="normal" if ready and producer_state != 3 else "disabled")
        self.resume_worker.configure(state="normal" if ready and producer_state == 3 else "disabled")

    def start(self, action):
        if self.job is not None:
            return
        env = tool_environment()
        folder = ROOT / "build/console"
        folder.mkdir(parents=True, exist_ok=True)
        self.session = Path(tempfile.mkdtemp(prefix="run-", dir=folder))
        env.update(PYTHONUNBUFFERED="1")
        path = self.session / (action + ".log")
        elf = (ROOT / {"arm":"build/arm/cortex_m3_demo.elf",
                       "freertos":"build/freertos/freertos_cortex_m3_demo.elf",
                       "zephyr":"build/zephyr/kernel/zephyr/zephyr.elf",
                       "sensor":"build/zephyr/sensor/zephyr/zephyr.elf"}.get(action, "build"))
        command = [sys.executable, ROOT / "scripts/vel.py", action]
        if action == "inspector":
            command = [sys.executable, ROOT / "scripts/vel_inspector.py"]
        elif action == "gateway":
            busy, owner = lock_status(work("gateway_stage8_3_ws") / "accept.lock")
            if busy:
                self.status.set("网关已有任务，请在原终端检查 jobs -l 或等待结束。")
                return
            command.extend(["--mode", "all"])
        elif elf.is_file():
            if action == "arm":
                command = [sys.executable, ROOT / "scripts/run_qemu.py", "--elf", elf]
            elif action == "freertos":
                command = [sys.executable, ROOT / "scripts/run_stage3.py", "--elf", elf, "--mode", "scheduler"]
                env["VEL_STAGE3_EVIDENCE"] = str(self.session)
            else:
                case = "sensor" if action == "sensor" else "kernel"
                command = [sys.executable, ROOT / "scripts/stage4_case.py", case]
                env["VEL_STAGE4_EVIDENCE"] = str(self.session)
        else:
            target = "zephyr" if action == "sensor" else action
            self.status.set(f"固件还未构建。请先在终端运行 python3 scripts/vel.py {target}。")
            return
        self.log = path
        if action == "inspector":
            self.inspector_log = path
            self.command_pending = None
            self.tabs.select(2)
        self.log_choice.set("本次任务")
        self.job_name = action
        try:
            with path.open("w") as output:
                self.job = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                            stdin=subprocess.PIPE if action == "inspector" else None,
                                            stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            self.status.set(str(error))
            return
        self.stop_at = None
        for button in self.buttons:
            button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set(f"正在运行 {action} · PID {self.job.pid}")

    def cancel(self):
        if self.job and self.job.poll() is None and self.stop_at is None:
            self.status.set("正在停止并清理本次任务…")
            try:
                if self.job_name == "inspector":
                    os.killpg(self.job.pid, signal.SIGTERM)
                else:
                    self.job.terminate()
            except ProcessLookupError:
                pass
            self.stop_at = time.monotonic() + 18
            self.stop_button.configure(state="disabled")

    def close(self):
        self.closing = True
        if self.job and self.job.poll() is None:
            self.cancel()
        else:
            self.window.destroy()

    def refresh(self):
        if self.job:
            rc = self.job.poll()
            if rc is None and self.stop_at and time.monotonic() >= self.stop_at:
                try:
                    os.killpg(self.job.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif rc is not None:
                result = "已停止" if self.stop_at else ("通过" if rc == 0 else f"失败 · 退出码 {rc}")
                self.status.set(f"{self.job_name} · {result} · 日志见「日志」页")
                if self.job.stdin:
                    self.job.stdin.close()
                self.job = None
                self.stop_button.configure(state="disabled")
                for button in self.buttons:
                    button.configure(state="normal")
        if self.closing and self.job is None:
            self.window.destroy()
            return
        self.refresh_inspector()
        busy, owner = lock_status(work("gateway_stage8_3_ws") / "accept.lock")
        self.lock_text.set(f"网关工作区 · {'运行中，PID '+str(owner.get('pid', '未知')) if busy else '空闲'}")
        for table, sources in self.tables.items():
            for name in sources:
                values, stamp, path = read_sample(name)
                if path:
                    self.sample_paths[name] = path
                sample_time = datetime.fromtimestamp(stamp).strftime("%m-%d %H:%M:%S") if stamp else "暂无"
                table.set(name+":source", "value", sample_time)
                for key in METRICS[name].values():
                    table.set(name+":"+key, "value", values.get(key, "—"))
        choice = self.log_choice.get()
        path = self.log if choice == "本次任务" else self.sample_paths.get(choice)
        if path:
            text = tail(path, 18000)
            self.log_path.configure(text=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))
            if self.last_log != (path, text):
                at_end = self.log_box.yview()[1] >= .99
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", "end")
                self.log_box.insert("1.0", text)
                self.log_box.configure(state="disabled")
                if at_end:
                    self.log_box.see("end")
                self.last_log = (path, text)
        else:
            self.log_path.configure(text="暂无日志")
            if self.last_log:
                self.log_box.configure(state="normal")
                self.log_box.delete("1.0", "end")
                self.log_box.configure(state="disabled")
                self.last_log = None
        self.window.after(850, self.refresh)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--advanced", action="store_true", help="open the register and RTOS monitor")
    parser.add_argument("--live", action="store_true", help="start the live firmware on launch")
    parser.add_argument("--self-test", action="store_true", help="initialize and exercise the WSLg window")
    args = parser.parse_args()
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise SystemExit(f"无法打开窗口，请确认当前 WSL 已启用 WSLg。{error}")
    if not (args.live or args.advanced or args.self_test):
        from vel_gui_workbench import Workbench
        Workbench(root, advanced=lambda window: Dashboard(window))
        root.mainloop()
        return 0
    app = Dashboard(root)
    if args.live and not args.self_test:
        root.after_idle(lambda: app.start("inspector"))
    if args.self_test:
        app.start("arm")
        deadline = time.monotonic() + 20

        def check():
            if app.job is not None and time.monotonic() < deadline:
                root.after(80, check)
                return
            found = app.log and "[MAIN] PASS" in tail(app.log)
            if not found:
                app.cancel()
            print("DASHBOARD_SMOKE_PASS" if found else "DASHBOARD_SMOKE_FAIL", flush=True)
            app.close()
            main.exit_status = 0 if found else 1

        root.after(100, check)
    root.mainloop()
    return getattr(main, "exit_status", 0)


if __name__ == "__main__":
    sys.exit(main())
