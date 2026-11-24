# GUI-H1 架构

默认 dashboard 使用 Tkinter 工作台。--advanced 和 --live 保留原来的寄存器与实时 FreeRTOS 监控。界面以 after 轮询本次会话日志，依赖检查在工作线程完成。注册表定义模式与固定参数，执行前再次校验，用户选择不会拼成 shell 命令。

vel_gui_job 持有功能锁，给实验提供独立工作区和证据目录，并保存命令、时刻、会话状态和退出码。它先温和停止所拥有的进程组，再按时限清理由 Linux subreaper 收养的子进程，包括旧测试另建会话的进程。关闭主窗口会等清理完成。高级监控可独立启动；从工作台打开时随主窗口清理。

Modbus 主站与 Tk 界面分进程。主站构建现有 Stage 8.2 从站，使用从站实际创建的 PTY，经 pymodbus 发出 FC01/02/03/04/05。读回的 FC01 状态与 IR7 以及 HR3 位图比对后才显示确认。DI 控件单独通过从站 UART0 既有仿真刺激接口改变虚拟输入，再使用 RTU FC02 与 IR6 确认。在 图形界面没有本地 GPIO 镜像。115 秒仿真会话到达上限后自动清理，也可手动停止。

每次交互保存 console.log、build.log、slave.log、rtu-wire.jsonl、slave-exit.json 和 result.json。LIVE 仅用于当前会话；历史记录显示时间与会话 ID，未产生数据时显示 N/A。CAN 等测试统计来自其原验收 JSON。
