# GUI-H1 功能与边界

| 功能 | 后端 | GUI 操作 |
| --- | --- | --- |
| Cortex-M3 | QEMU | 运行已构建的固件并检查 UART、SysTick、异常 |
| FreeRTOS | QEMU | CTest 调度、FatFs 和调试。高级窗口另有实时任务监控 |
| Zephyr 内核 | QEMU | 运行已构建的内核样例，显示实际任务和定时器计数 |
| GPIO / EXTI | Renode | 运行现有模拟 GPIO 和外部中断验收 |
| CAN | native_sim | 仅回环测试，显示发送、接收与一致性验证结果 |
| Modbus RTU | native_sim / PTY | 独立会话，单路 DO 控制与回读；DI 仿真刺激；寄存器读取；协议及故障测试 |
| Modbus TCP Gateway | native_sim | 快速故障检查或完整网关验收 |
| FatFs | Host | CTest 块设备及 FatFs 测试 |
| ROS 2 | Host | 已安装发行版的真实话题和服务检查 |
| micro-ROS / 完整历史链 | QEMU / XRCE / 多后端 | UNAVAILABLE，依赖 Lyrical 及未恢复的构建锁 |
| 物理硬件、RS485 电气特性 | — | NOT TESTED |

GUI 不执行完整历史回归。Modbus 为独立模拟从站，操作不触及真实硬件。CAN 页暂无自定义发送 API。缺少 WSLg 时，仍可运行 CLI 验收和 GUI-H1 的 headless 检查。
