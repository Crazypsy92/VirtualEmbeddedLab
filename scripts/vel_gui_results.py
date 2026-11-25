"""Summarize specific measured fields. A job's supervisor supplies its outcome."""
import json
import re


def json_report(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def output_summary(feature, folder):
    if feature == "i2c":
        result = json_report(folder / "i2c-summary.json")
        return f"{result.get('backend', 'SIMULATED')} · 事务 {result.get('transactions', 'N/A')}"
    if feature in ("gpio", "can"):
        backend = "renode" if feature == "gpio" else "native_sim"
        result = json_report(folder / "stage8_1_evidence" / backend / "acceptance.json")
        keys = (("中断边沿", "exti_edges"), ("UART 帧", "uart_frames")) if feature == "gpio" else (
            ("CAN 发送", "can_sent"), ("CAN 接收", "can_received"),
            ("GPIO 翻转", "gpio_toggles"), ("输入边沿", "input_edges"))
        if result.get("status") != "PASS":
            return "N/A · 缺少完成后的测量"
        return "  ·  ".join(f"{title} {result.get(key, 'N/A')}" for title, key in keys)
    if feature == "gateway":
        r = folder / "stage8_3_evidence"
        groups = json_report(r/"tests_all.json")
        if not groups:
            groups = json_report(r/"tests_fault.json")
        cross = json_report(r/"rtu/consistency.json")
        return f"网关测试组 {groups.get('tests', 'N/A')}  ·  独立状态比对 {cross.get('status', 'N/A')}"
    if feature == "reliability":
        files = sorted((folder/"work/gateway_stage8_3_1_ws").glob("accept-*/acceptance.json"))
        steps = json_report(files[-1]).get("steps", {}) if files else {}
        return "  ·  ".join(f"{name} exit={data.get('exit', 'N/A')}" for name, data in steps.items()) or "N/A"
    path = folder / "console.log"
    if not path.is_file():
        return "N/A"
    text = path.read_text(errors="replace")
    if feature in ("freertos", "fatfs"):
        match = re.search(r"(\d+)% tests passed, (\d+) tests failed out of (\d+)", text)
        if match:
            return f"CTest {int(match[3])-int(match[2])}/{match[3]}"
    if feature == "arm":
        values = re.findall(r"\[TICK\] (?:first|final)=(\d+)", text)
        if len(values) == 2:
            return f"SysTick {values[0]} → {values[1]}"
    if feature == "zephyr":
        log = folder / "stage4_evidence/stage4_1/kernel.log"
        stats = dict(re.findall(r"\[STAT\] (\w+)=(\d+)", log.read_text())) if log.is_file() else {}
        if stats:
            return f"任务 A/B {stats.get('worker_a', 'N/A')}/{stats.get('worker_b', 'N/A')}  ·  定时器 {stats.get('timer', 'N/A')}"
    if feature == "ros":
        result = json_report(folder / "stage5_evidence/stage5_0/runtime_gate.json")
        if result:
            return f"消息 {result.get('listener_received', 'N/A')}  ·  服务结果 {result.get('service_sum', 'N/A')}"
    return "详情见日志"
