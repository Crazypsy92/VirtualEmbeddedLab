# 实验控制台验收 · 2026-11-24

已在 Bridge-Ubuntu-24.04 的迁移后工程中复测。实时演示使用 QEMU MPS2 AN385、Cortex-M3 和 FreeRTOS V11.2.0。启动命令为 python3 scripts/vel.py dashboard --live，需要 WSLg。

| 检查 | 结果 |
| --- | --- |
| 独立演示固件 | 编译成功，QEMU 启动并连续输出结构化快照 |
| 内核寄存器 | 读到 CPUID、ICSR、VTOR、SysTick LOAD/VAL、NVIC ISER0/ISPR0 |
| UART0 | CTRL=3，BAUDDIV=217，成功收取窗口发出的两条命令 |
| APB Timer 0 | CTRL=1，RELOAD=25,000,000，VALUE 在有效范围内，窗口选择该项后显示寄存器 |
| RTOS 任务 | 实际枚举 Inspector、Producer、Consumer、IDLE 4 个任务，显示真实状态、优先级和栈余量 |
| 操作回路 | 窗口挂起 Producer 后状态变为挂起且计数停止，恢复后计数继续增长 |
| 关闭窗口 | 本轮 QEMU 子进程已退出 |
| FreeRTOS 回归 | CTest 14/14，通过调度、GDB、FatFs、数据记录和故障测试 |

外设页区分实时采样与仅有模型的设备。SPI、I²C 等目前只展示模型和地址，未运行总线交易。AN385 的 GPIO 是 QEMU 占位模型，历史页中的虚拟 GPIO 数据来自另一个 native_sim 后端。没有测试物理硬件。该报告只覆盖控制台变更，本次不包含 Stage 8.3.1 的 30 分钟专项。

本机验收日志位于 build/console/run-pxozcb9f/inspector.log 和 build/freertos/Testing/Temporary/LastTest.log。实时监控值与任务队列来自独立演示固件，历史页继续读取各自的仿真日志。

模型来源：[QEMU 8.2.2 MPS2 板级模型](https://github.com/qemu/qemu/blob/v8.2.2/hw/arm/mps2.c)、[CMSDK UART](https://github.com/qemu/qemu/blob/v8.2.2/hw/char/cmsdk-apb-uart.c)、[CMSDK APB Timer](https://github.com/qemu/qemu/blob/v8.2.2/hw/timer/cmsdk-apb-timer.c)、[FreeRTOS 任务状态 API](https://github.com/FreeRTOS/FreeRTOS-Kernel/blob/V11.2.0/include/task.h)。
