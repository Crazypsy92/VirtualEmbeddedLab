"""Folded one-shot/bounded injection controls for the existing RTU inspector."""
import tkinter as tk
from tkinter import ttk

from vel_rtu_fault_rules import RULES


class FaultControls(ttk.Frame):
    def __init__(self, parent, send, clear):
        super().__init__(parent)
        self.send = send
        self.active = False
        self.running = False
        self.remaining = self.completed = 0
        self.selected_rule = None
        self.scheduled = None
        self.direction = tk.StringVar(value="主站 → 从站")
        self.preset = tk.StringVar()
        self.count = tk.StringVar(value="1")
        self.status = tk.StringVar(value="每笔注入后自动验证无故障 FC03。")
        self.open = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="故障注入", variable=self.open, command=self.toggle).pack(anchor="w")
        self.body = ttk.Frame(self)
        head = ttk.Frame(self.body)
        head.pack(fill="x", pady=2)
        direction = ttk.Combobox(head, values=("主站 → 从站", "从站 → 主站"), textvariable=self.direction,
                                 width=13, state="readonly")
        direction.pack(side="left", padx=(0, 5))
        direction.bind("<<ComboboxSelected>>", self.update_presets)
        self.choices = ttk.Combobox(head, textvariable=self.preset, width=19, state="readonly")
        self.choices.pack(side="left", padx=(0, 6))
        ttk.Label(head, text="次数").pack(side="left")
        ttk.Entry(head, textvariable=self.count, width=5).pack(side="left", padx=4)
        self.start = ttk.Button(head, text="启动注入", command=self.begin, state="disabled")
        self.start.pack(side="left", padx=3)
        self.stop = ttk.Button(head, text="停止注入", command=self.cancel, state="disabled")
        self.stop.pack(side="left", padx=3)
        ttk.Button(head, text="清除注入显示", command=lambda: self.clear(clear)).pack(side="left", padx=3)
        ttk.Label(self.body, textvariable=self.status, wraplength=860).pack(anchor="w", pady=3)
        self.update_presets()

    def toggle(self):
        if self.open.get():
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()

    def update_presets(self, _event=None):
        key = "tx" if self.direction.get() == "主站 → 从站" else "rx"
        self.choices.configure(values=[rule.label for rule in RULES.values() if rule.direction == key])
        self.choices.current(0)

    def enable(self, active):
        self.active = active
        self.start.configure(state="normal" if active and not self.running else "disabled")
        self.stop.configure(state="normal" if self.running else "disabled")
        if active and self.running and self.remaining and self.scheduled is None:
            self.scheduled = self.after_idle(self.next)

    def begin(self):
        try:
            count = int(self.count.get())
            if not 1 <= count <= 20:
                raise ValueError
        except ValueError:
            self.status.set("请输入 1–20 次。")
            return
        self.selected_rule = next(key for key, rule in RULES.items() if rule.label == self.preset.get())
        self.remaining, self.completed, self.running = count, 0, True
        self.enable(self.active)

    def next(self):
        self.scheduled = None
        if self.running and self.active and self.remaining:
            self.remaining -= 1
            self.status.set(f"{RULES[self.selected_rule].label} · 等待从站与恢复结果")
            self.send({"op": "fault", "rule": self.selected_rule})

    def outcome(self, event):
        self.completed += 1
        passed = event["expectation_met"] and event["recovered"] and event["state_unchanged"]
        self.status.set(f"{RULES[event['rule']].label} · 命中 {self.completed} · {event['observed']} · "
                        f"#{event['recovery_sequence']} {'RECOVERED' if event['recovered'] else '恢复失败'} · "
                        f"{'状态未改变' if event['state_unchanged'] else '状态核对失败'}"
                        + (" · 与预期不符" if not event["expectation_met"] else ""))
        if not self.remaining or not passed:
            self.cancel(report=False)

    def cancel(self, report=True):
        self.running = False
        self.remaining = 0
        if self.scheduled is not None:
            self.after_cancel(self.scheduled)
            self.scheduled = None
        if report:
            self.status.set("已停止安排后续注入；在途事务完成后仍会验证恢复。")
        self.enable(self.active)

    def clear(self, clear_rows):
        clear_rows()
        if not self.running:
            self.status.set("已清除注入显示。原始会话日志仍保留。")

    def destroy(self):
        self.cancel(report=False)
        super().destroy()
