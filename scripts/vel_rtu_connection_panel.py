"""Editable RTU transport parameters for the existing Tk workbench."""
from dataclasses import asdict
import tkinter as tk
from tkinter import ttk

from vel_rtu_connection import RtuConnection


class ConnectionPanel(ttk.Frame):
    def __init__(self, parent, connect, disconnect, probe):
        super().__init__(parent)
        self.backend = tk.StringVar(value="PTY 仿真")
        self.fixture = tk.BooleanVar()
        self.expanded = tk.BooleanVar()
        self.message = tk.StringVar(value="PTY · 未连接")
        self.busy = False
        self.entries = {}
        self.serial_fields = []
        self.endpoints = ttk.Frame(self)
        self.toggle = ttk.Checkbutton(self.endpoints, text="连接 / 传输配置",
                                     variable=self.expanded, command=self.show)
        self.toggle.pack(side="left")
        ttk.Label(self.endpoints, textvariable=self.message, wraplength=760).pack(side="left", padx=6)
        self.endpoints.pack(fill="x")
        self.body = ttk.Frame(self)
        self.selector = ttk.Combobox(self.body, state="readonly", values=("PTY 仿真", "Serial 设备"),
                                    width=14, textvariable=self.backend)
        self.selector.grid(row=0, column=0, sticky="w")
        self.selector.bind("<<ComboboxSelected>>", self.change)
        self.fixture_control = ttk.Checkbutton(self.body, text="仅用 native_sim PTY 验证 Serial",
                                               variable=self.fixture, command=self.change)
        self.fixture_control.grid(row=0, column=1, columnspan=3, sticky="w")
        self.connect_button = ttk.Button(self.body, text="连接", command=connect)
        self.connect_button.grid(row=0, column=4, padx=3)
        self.disconnect_button = ttk.Button(self.body, text="断开", command=disconnect)
        self.disconnect_button.grid(row=0, column=5, padx=3)
        self.probe_button = ttk.Button(self.body, text="测试连接", command=probe)
        self.probe_button.grid(row=0, column=6, padx=3)
        fields = (("port", "端口", "/dev/ttyUSB0", 17), ("baudrate", "波特率", "115200", 9),
                  ("bytesize", "数据位", "8", 4), ("parity", "校验", "N", 4),
                  ("stopbits", "停止位", "1", 4), ("read_timeout", "读超时 s", "0.15", 6),
                  ("write_timeout", "写超时 s", "0.15", 6), ("inter_byte_timeout", "字节间 s", "", 6))
        for i, (key, label, default, width) in enumerate(fields):
            var = self.entries[key] = tk.StringVar(value=default)
            field = ttk.Frame(self.body)
            field.grid(row=1 + i // 5, column=i % 5, sticky="w", padx=(0, 4), pady=2)
            ttk.Label(field, text=label).pack(side="left")
            box = ttk.Entry(field, textvariable=var, width=width)
            box.pack(side="left", padx=(2, 0))
            self.serial_fields.append((field, box))
        self.change()

    def selection(self):
        return (self.backend.get(), self.fixture.get(), self.expanded.get(),
                {key: var.get() for key, var in self.entries.items()})

    def restore(self, selection):
        backend, fixture, expanded, fields = selection
        self.backend.set(backend)
        self.fixture.set(fixture)
        self.expanded.set(expanded)
        for key, value in fields.items():
            self.entries[key].set(value)
        self.change()
        self.show()

    @property
    def simulation(self):
        return self.backend.get() == "PTY 仿真" or self.fixture.get()

    def show(self):
        if self.expanded.get():
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()

    def change(self, _event=None):
        serial = self.backend.get() == "Serial 设备"
        for frame, _ in self.serial_fields:
            if serial:
                frame.grid()
            else:
                frame.grid_remove()
        if serial:
            self.fixture_control.grid()
            if self.fixture.get():
                self.serial_fields[0][0].grid_remove()
        else:
            self.fixture_control.grid_remove()
        if not self.busy:
            self.message.set(("Serial" if serial else "PTY") + " · 未连接")

    def configuration(self, probe):
        if self.backend.get() == "PTY 仿真":
            return asdict(RtuConnection()) | {"probe": probe}
        values = {key: variable.get().strip() for key, variable in self.entries.items()}
        port = values.pop("port")
        for key in ("baudrate", "bytesize"):
            values[key] = int(values[key])
        for key in ("stopbits", "read_timeout", "write_timeout"):
            values[key] = float(values[key])
        values["inter_byte_timeout"] = float(values["inter_byte_timeout"]) if values["inter_byte_timeout"] else None
        if self.fixture.get():
            port = ""
        return asdict(RtuConnection("serial", self.fixture.get(), port, values)) | {"probe": probe}

    def controls(self, *, executable, busy, active, pending):
        self.busy = busy
        self.selector.configure(state="disabled" if busy else "readonly")
        self.fixture_control.configure(state="disabled" if busy else "normal")
        for _, widget in self.serial_fields:
            widget.configure(state="disabled" if busy else "normal")
        self.connect_button.configure(state="normal" if executable and not busy else "disabled")
        self.disconnect_button.configure(state="normal" if busy else "disabled")
        self.probe_button.configure(state="normal" if (active and not pending) or (executable and not busy) else "disabled")

    def result(self, metadata, probe=None):
        name = metadata.get("scope", metadata.get("backend", "RTU"))
        port = metadata.get("configuration", {}).get("port") or "—"
        state = "已连接" if metadata.get("connected") else "未连接"
        probe = metadata.get("probe") if probe is None else probe
        if probe is not None:
            state += f" · FC03 通过（HR0={probe[0]}）"
        if metadata.get("error"):
            state += " · " + metadata["error"]
        self.message.set(f"{name} · {port} · {state}")
