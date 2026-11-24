# GUI-H1 验收 · 2026-11-24

基线 4fa470ac3df4b8459fca2dc8eccb13aad70c7ef9。环境为 Bridge-Ubuntu-24.04、WSLg/Tkinter、Zephyr 4.4.2 native_sim、pymodbus 3.11.4。验收显示实际本机行为。Hardware、物理 RS485 和 Ethernet 为 NOT TESTED。

| 检查 | 结果 |
| --- | --- |
| python3 scripts/accept_gui_h1.py | 7/7，通过注册表、参数、进程生命周期和真实 WSLg 窗口 |
| python3 scripts/accept_gui_h1.py --headless | 6/6（DISPLAY 和 WAYLAND_DISPLAY 为空） |
| 工作台关闭 | 实际等待 RTU 进程退出。独立验证高级窗口实时 QEMU 随主窗口退出 |
| 旧界面入口 | dashboard --self-test 通过，得到 Cortex-M3 UART 结果 |
| RTU GPIO | DO_0 由 FC05 置 1 后由 FC01 与 IR7 确认为 1，再置 0 并回读为 0。FC02 和 IR6 读回 DI 位图 0101。FC03 与 FC04 均返回 8 个寄存器 |
| 独立注册入口 | CAN、Renode GPIO/EXTI、Host FatFs、Zephyr 内核、ROS 2 依次运行，退出码均为 0 |
| Stage 8.3 Gateway | 7 组通过。6 项运行检查及独立 TCP/RTU 状态比对 |
| Stage 8.2 RTU fault | PASS |
| Stage 8.2 RTU protocol | **FAIL**。1000 笔旧测试出现一次无应答后停止，复跑仍出现于不同请求。延长等待及增加请求间距的诊断尝试也未消除，未保留对旧测试的改动。没有自动重试写入 |
| Stage 0–7 历史全量 133 项 | NOT RUN，现有 Lyrical / micro-ROS 构建依赖未恢复 |
| Stage 8.3.1 独立压力和耐久 | NOT RUN，本轮范围为 GUI-H1 |

本轮 GUI 验收的原始文件位于 build/workspaces/gui-h1/runs/rtu-odkbvc2f/。rtu-wire.jsonl 包含请求与响应；两条 FC05 命令 PDU 分别以 01050000ff00 和 010500000000 开头。console.log 保存 DO、DI、HR3、IR6、IR7 的前后读回。slave.log 包含实际 GPIO 统计和 INPUT bits=5。result.json 的 CANCELLED 是关闭窗口的预期生命周期结果，与会话中已确认的写入回读分别记录。slave-exit.json 保存从站退出结果。

测试索引：build/gui-h1-delivery.log（WSLg），build/gui-h1-final-tests.log（headless 和旧界面），build/gui-entry-urg4iqzr/（独立入口），build/gui-h1-regression/regression-vn4n77vi/（Gateway 和 RTU fault）。RTU protocol 复现日志保存在 build/gui-h1-regression/baseline-final/protocol.log；对应请求/响应在共用回归工作区的 modbus_stage8_2_ws/runs/master-*/wire.json。大日志与构建留在本机 build 目录。
