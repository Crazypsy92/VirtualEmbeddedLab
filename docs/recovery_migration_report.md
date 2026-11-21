# 当前 WSL 迁移与复测

工程位于 WSL Ubuntu 中的本仓库目录，以普通用户身份运行。运行入口为 scripts/vel.py。脚本统一从工程位置和 VEL 配置解析路径；工作区、工具、测试日志默认位于 build。没有初始化项目 Git 仓库，也没有提交。

## 已复测

| 范围 | 结果 |
| --- | --- |
| Host Debug、Release、Sanitizer | 各 20/20 |
| Cortex-M3、UART、异常和 GDB | 6/6 |
| FreeRTOS、FatFs 及故障用例 | 14/14 |
| Zephyr Cortex-M3 | 18/18。设备树、传感器和 7 个采集场景通过 |
| Stage 8.1 native_sim、Renode | native_sim 4/4，Renode 3/3 |
| Stage 8.2 Modbus RTU | protocol 和 fault 均通过 |
| Stage 8.3 Modbus Gateway | 现有运行用例 6/6，独立状态交叉检查通过 |
| Stage 8.3.1 快速专项 | 400 次完全相同的 TID 并发，8 个 RTU 延迟用例，TCP 字节流含慢速半帧截止时间，100 轮故障恢复 |
| Stage 8.3.1 压力 | 10,000 次正常混合事务通过，用时 464.01 秒，实际写入计数 4,996。Gateway FD 由空闲 7 个升至并发中的 11 个，结束后回到 7 个 |
| ROS 2 Jazzy | 环境、话题和服务、主机桥接已验证。独立 QEMU 到 ROS 2 端到端传输 256 条、每路传感器 128 条 |

Stage 3 合并复测统计为 80/80。加上 Zephyr CTest 的 18 项，本轮实际通过 Stage 0–4 共 98 项。旧的 Stage 3 分阶段存档没有恢复，报告归档状态与本次实际通过数分别记录。并行运行时，原 GDB 用例偶尔在 Reader 的 FatFs 调用中断下，且宿主调度会扰动 RTOS tick。改用具有 Logger 任务条件的断点，并以 QEMU 指令时钟控制调试运行。三个 GDB 用例分别连续通过三次，随后整套复测通过。

Zephyr 采集故障场景 2 原本调用驱动不支持的 SENSOR_ATTR_PRIV_START 写接口。改为在该场景的设备树中使用已有 fail-after 属性，确认传感器 A 成功采样 7 次后返回 EIO。其他采集场景仍按原协议运行。

ROS 2 端到端测试使用同一 ROS Service 客户端及时发送 STOP，验证统计值停止增长，再设置采样周期后重新启动。首次全套 CTest 中 E2E 超时窗口未满足，从而阻塞依赖 E2E 证据的故障用例。修复后分别在 CTest 重跑了 E2E 和故障用例，两项都通过，10 个 Stage 5 项目均有本轮通过记录。

Renode 版本仍为原锁定的 1.17.0。官方包 SHA-256 通过历史锁核对。原始平台文件不变，每次运行生成本地副本，仅省去启动时联网请求的符号描述。20 次串口回显、10 条中断边沿及 GDB 检查均通过。SocketCAN 环境缺少 CAP_NET_ADMIN，未创建宿主接口。

## RTU 和 TCP 修复

实际修复前记录显示 A 超时后，B 返回了 A 的寄存器值 17，B 正确值为 600。另有一份前置探测同时释放两帧，产生后端异常，不能作为串线证据。修复后的专项在 B 已经提交到 TCP 的情况下释放真实旧 RTU 字节，验证 B 只返回 600。Gateway 在 RTU 错误后按上一请求开始时间计算隔离，声明的最大响应年龄为 1,000 ms，另留 250 ms 余量。清理输入后再重置 RTU 客户端。保护范围取决于延迟上限，RTU 缺少事务 ID，任意长延迟下无法判别响应归属。超时写入不自动重发，不能据此保证只执行一次。

TCP 半帧的 1 秒截止时间从该帧开始计算。慢速发送后续字节不会延长期限，已用真实 TCP socket 验证。

## 验收范围和日志

- 原始失败与修复前串线证据在 evidence/stage8_3_1/rtu_late。
- Stage 3 合并复测在 build/migration-stage3-final。
- Zephyr 18 项报告在 build/migration-stage4-final/ctest.xml。
- 最终 Stage 8.3 网关验收在 build/workspaces/gateway_stage8_3_ws/accept-xh9mczy3。
- native_sim 和 Renode 验收在 build/migration-stage8-1-native 和 build/migration-stage8-1-renode-final。
- Stage 8.3.1 快速回归在 build/final-recheck/gateway_stage8_3_1_ws/accept-fqcd1icq。
- Stage 8.3.1 压力记录在 build/workspaces/gateway_stage8_3_1_ws/accept-roau5056。这是最初隔离修复后的构建，之后调整的提前错误隔离和半帧期限已在最终快速回归中测试。
- 独立的 Jazzy 端到端记录在 build/migration-final-e2e。

没有以旧 Git 提交或旧测试日志代替这些结果。Stage 6/7 的 micro-ROS 锁和匹配的 Lyrical 环境仍待恢复。Stage 8.3.1 的真实 30 分钟模式可通过入口启动，本轮没有执行。物理 Ethernet、RS485 和硬件未测试。

## 实验控制台与终端暂停

入口为 python3 scripts/vel.py dashboard。WSLg 窗口显示 Cortex-M3、Zephyr、FreeRTOS、GPIO 和 Modbus 的真实日志与最近采样时间。已实际打开窗口，启动 Cortex-M3 读取 UART，并用停止按钮取消该窗口启动的网关任务。终端锁竞争退出 75 并说明恢复操作。Ctrl+Z 取消验证的退出码为 130，验收记录为 CANCELLED，工作区锁已释放。
