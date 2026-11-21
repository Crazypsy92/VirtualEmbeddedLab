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
        for label, action in [("运行 Cortex-M3", "arm"), ("运行 Zephyr 内核", "zephyr"),
                              ("运行 FreeRTOS", "freertos"), ("运行外设测试", "sensor"),
                              ("运行网关验收", "gateway")]:
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
        for title, sources in VIEWS:
            view = ttk.Frame(self.tabs, padding=12)
            self.tabs.add(view, text=title)
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
        if action == "gateway":
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
        self.log_choice.set("本次任务")
        self.job_name = action
        try:
            with path.open("w") as output:
                self.job = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
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
            self.job.terminate()
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
                self.job = None
                self.stop_button.configure(state="disabled")
                for button in self.buttons:
                    button.configure(state="normal")
        if self.closing and self.job is None:
            self.window.destroy()
            return
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
    parser.add_argument("--self-test", action="store_true", help="initialize and exercise the WSLg window")
    args = parser.parse_args()
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise SystemExit(f"无法打开窗口，请确认当前 WSL 已启用 WSLg。{error}")
    app = Dashboard(root)
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
