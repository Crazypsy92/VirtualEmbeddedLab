"""Fixed allowlist for the GUI. No user text enters a shell or a command path."""
from dataclasses import dataclass
import subprocess
import sys

from vel_env import ROOT, ros_setup, tool, tool_environment, work, zephyr_base


@dataclass(frozen=True)
class Feature:
    id: str
    title: str
    category: str
    backend: str
    description: str
    modes: dict
    dependencies: tuple = ()
    evidence: str = "退出码与原始日志"
    unavailable: str = ""


FEATURES = (
    Feature("arm", "Cortex-M3", "MCU / RTOS", "QEMU", "检查 UART、SysTick 和异常入口。",
            {"单项实验": ("run_qemu.py",)}, ("qemu-system-arm", "arm ELF")),
    Feature("freertos", "FreeRTOS", "MCU / RTOS", "QEMU", "构建并运行调度、FatFs 和调试测试。",
            {"单项实验": ("vel.py", "freertos")}, ("arm-none-eabi-gcc", "cmake", "ninja", "qemu-system-arm", "gdb-multiarch")),
    Feature("zephyr", "Zephyr 内核", "MCU / RTOS", "QEMU", "检查调度、定时器、工作队列和栈。",
            {"单项实验": ("stage4_case.py", "kernel")}, ("qemu-system-arm", "Zephyr ELF")),
    Feature("gpio", "GPIO / EXTI", "GPIO / EXTI", "Renode", "运行 STM32F103 模拟 GPIO、外部中断和 UART 检查。",
            {"单项实验": ("accept_stage8_1.py", "--backend", "renode")}, ("arm-none-eabi-gcc", "gdb-multiarch", "Renode cache")),
    Feature("can", "CAN Loopback · 帧实验台", "CAN", "Zephyr native_sim 软件 Loopback / CAN API 帧级",
            "发送 Classical CAN 标准帧与扩展帧，按 IDE 过滤并对照真实 TX/RX。",
            {"交互会话": ("vel_gui_can.py",),
             "单项实验": ("accept_stage8_1.py", "--backend", "native_sim")}, ("Zephyr",),
            "CAN API 事务 JSONL"),
    Feature("rtu", "Modbus RTU · 协议检查与 GPIO", "Modbus", "Zephyr native_sim / PTY",
            "执行八种 RTU 操作，查看真实帧、字段和 CRC，写入后复核设备状态。",
            {"交互会话": ("vel_gui_modbus.py",),
             "快速测试": ("accept_stage8_2.py", "--mode", "fault"),
             "协议与压力": ("accept_stage8_2.py", "--mode", "protocol")},
            ("Zephyr", "Modbus Python"), "逐帧 PTY JSONL · GPIO / 寄存器回读"),
    Feature("gateway", "Modbus TCP Gateway", "Modbus", "Zephyr native_sim / TCP",
            "现有网关测试，包含实验所选范围的从站和网关构建。",
            {"快速测试": ("accept_stage8_3.py", "--mode", "fault"),
             "完整网关验收（约 2 分钟）": ("accept_stage8_3.py", "--mode", "all")},
            ("Zephyr", "Modbus Python")),
    Feature("fatfs", "FatFs 虚拟存储", "FatFs", "Host / CTest", "运行主机及 FatFs 测试，无需挂载实体磁盘。",
            {"单项实验": ("vel.py", "host")}, ("cmake", "ninja", "gcc")),
    Feature("ros", "ROS 2", "ROS 2 / micro-ROS", "Host ROS 2", "运行已安装 ROS 2 的话题与服务示例。",
            {"单项实验": ("stage5_ros_basic.py",)}, ("ROS 2 demos",)),
    Feature("micro", "micro-ROS", "ROS 2 / micro-ROS", "QEMU / XRCE",
            "原 Stage 6/7 需要匹配的 Lyrical 环境和依赖锁。", {},
            unavailable="当前入口需要恢复并核验原依赖，未启用。"),
    Feature("reliability", "网关可靠性", "自动化验收", "native_sim", "运行同 TID、延迟 RTU、TCP 字节流与恢复。",
            {"快速测试（约 2 分钟）": ("accept_stage8_3_1.py", "--mode", "quick")},
            ("Zephyr", "Modbus Python")),
    Feature("history", "Stage 0–7 历史回归", "自动化验收", "多后端",
            "完整历史回归需有原依赖与基线。", {}, unavailable="本机 micro-ROS 依赖未恢复。"),
)

BY_ID = {feature.id: feature for feature in FEATURES}
CATEGORIES = ("系统概览", "MCU / RTOS", "GPIO / EXTI", "CAN", "Modbus", "FatFs",
              "ROS 2 / micro-ROS", "自动化验收", "日志与高级信息")


def capabilities(dependencies=None):
    env = tool_environment()
    def probe(command):
        try:
            return subprocess.run(command, env=env, timeout=7, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    arm = ROOT / "build/arm/cortex_m3_demo.elf"
    zephyr = ROOT / "build/zephyr/kernel/zephyr/zephyr.elf"
    ros = False
    try:
        if dependencies is not None and "ROS 2 demos" not in dependencies:
            raise SystemExit
        setup = ros_setup()
        ros = probe(["bash", "-c", 'source "$1" && ros2 pkg prefix demo_nodes_cpp && ros2 pkg prefix demo_nodes_py',
                     "gui-ros", setup])
    except SystemExit:
        pass
    commands = {name: tool(name) != name for name in
                ("qemu-system-arm", "arm-none-eabi-gcc", "cmake", "ninja", "gdb-multiarch", "gcc")}
    return {**commands, "arm ELF": arm.is_file(), "Zephyr ELF": zephyr.is_file(),
            "Zephyr": (zephyr_base() / "VERSION").is_file() and tool("dtc") != "dtc"
                and commands["cmake"] and commands["ninja"]
                and probe([sys.executable, "-c", "import west, yaml, pykwalify, elftools"]),
            "Modbus Python": probe([sys.executable, "-c", "import pymodbus, serial"]),
            "ROS 2 demos": ros,
            "Renode cache": (work("simulation_stage8_1_ws") / "renode-1.17.0.tar.gz").is_file()}


def invocation(feature, mode, folder, available):
    item = BY_ID.get(feature)
    if item is None or not isinstance(mode, str) or mode not in item.modes:
        raise ValueError("Unknown feature or mode.")
    if missing := [dep for dep in item.dependencies if not available.get(dep)]:
        raise ValueError("Missing dependencies: " + ", ".join(missing))
    script, *args = item.modes[mode]
    path = ROOT / "scripts" / script
    if not path.is_file():
        raise ValueError(f"Missing entrypoint: {script}")
    if script in ("vel_gui_modbus.py", "vel_gui_can.py"):
        args.append(str(folder))
    return [sys.executable, str(path), *args]
