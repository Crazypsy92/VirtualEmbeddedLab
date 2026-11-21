# Stage 5.4 micro-ROS 可行性评估

调查日期：2026-10-27。结论：**DOCUMENTED；micro-ROS on Cortex-M3: NOT INTEGRATED**。本阶段的自定义 UART Bridge 是已运行的 ROS 2 ↔ QEMU 系统，不是 XRCE-DDS Client / Agent。

## 固定平台与证据等级

| 组件 | 已核对的上游信息 | 对本项目的结论 |
|---|---|---|
| micro_ros_setup / Client 构建入口 | 官方 lyrical 分支列出 Lyrical Supported，Linux Host Ubuntu 26.04，并支持 generate_lib 自定义交叉工具链 | 存在官方 Lyrical 构建路线；尚未在本项目交叉编译 Client |
| micro-ROS Agent | 官方 lyrical 分支存在，包装 Micro XRCE-DDS Agent，支持网络及串行传输 | 与 ROS 2 Lyrical 匹配的源码入口存在；未安装、未运行 Agent |
| Zephyr 集成模块 | 官方模块 main 的 README 声明测试 Zephyr 4.0.0 / 4.1.0；模块通过 ExternalProject 构建静态库，具有 Serial / UDP 选项 | **Zephyr 4.4.2 兼容性 UNVERIFIED**；不得把旧版本验证扩展为当前版本验证 |
| 旧 setup Zephyr 固件路径 | setup 表格列出 Zephyr 2.6.0、若干 STM32 板与 Host emulator | 不能直接用于本项目 4.4.2，更不能将 Host emulator 当作 MPS2 Cortex-M3 |
| FreeRTOS | setup 列有 FreeRTOS 平台及 STM32CubeMX 独立集成入口 | 存在移植路线；本项目固定 FreeRTOS 版本、MPS2 BSP、分配器与 UART 的组合仍需独立适配和验证 |
| QEMU MPS2-AN385 | QEMU 10.2.1 源码创建五个 CMSDK UART，按 serial_hd(i) 绑定；UART0 / UART1 已在本轮独立进程中验证双向收发 | 可复用 UART1 字节通道，不能复用本阶段 COBS 协议作为 XRCE 协议 |

上述“上游声明”只表示文档内容，**不等于本项目实测兼容**。本轮实测限于 Stage 5.0–5.3 自定义 Bridge。未找到并验证 Zephyr 4.4.2 + Lyrical + mps2/an385 的完整上游 CI 组合，故不宣称开箱即用。

## 传输选择

优先 UART1 + QEMU PTY：Agent 的 Linux serial / pseudoterminal 接口可接 PTY，MCU 侧注册 micro-ROS 自定义读写回调并保证超时及有界缓冲。当前 QEMU socket 仅承载 UART 字节流；直接将该 TCP socket 当作 Agent TCP XRCE 会混淆传输语义。Agent 支持 UDP/TCP/Serial/Custom 是官方能力；PTY 对接本目标的成功是**尚待验证的技术推断**。

QEMU AN385 源码还模型化 LAN9118；UDP 需要 Zephyr 网卡驱动、网络 Kconfig、地址配置及 QEMU 网络后端的单独验证。当前固件没有网络栈，未测试 UDP，因此本项目 UDP 路径为 UNVERIFIED。不需要真实 USB 或开发板。

## 内存与后续改动

当前 Bridge 固件静态统计见 [资源报告](stage5_memory.md)：ROM 段约 30 KiB、RAM 段约 9 KiB；它们**不是 micro-ROS 的资源消耗**。所选 AN385 的链接 RAM 区为 4 MiB，空间允许开展受控试验，但仍须实际链接后测量。

模块 Kconfig 的默认 XRCE MTU 为 512，历史槽数为 4。后续需显式限制节点、publisher、subscription、service 及流历史数量；按 MTU×历史槽数预留传输存储，再加入 rcl/rclc/rmw、消息对象、线程栈、对齐和分配器开销，不能用一个乘积代替总内存。当前 heap=0，若组件需要动态分配，需实现可控 allocator 并验证分配失败；还需线程栈水位、MAP、运行时高水位及 256 条记录验证。

后续独立任务应：锁定 lyrical Client/Agent 和 Zephyr 模块 commit；在外部依赖目录构建；核对 4.4.2 的 CMake/Kconfig/UART API；移植 UART1 自定义 XRCE transport；建立 Agent；以两路标准 Temperature 和控制服务重新验收；保持 Stage 5 Bridge 作对照。若 Zephyr 路线阻塞，可评估现有 FreeRTOS BSP + 静态库路线。均不在本轮实施。

本轮没有下载大型 Client/Agent 工作区，没有运行可选 Linux micro-ROS 演示，也没有给这些未执行项目标记 PASS。

## 原始来源

- [micro_ros_setup lyrical README](https://raw.githubusercontent.com/micro-ROS/micro_ros_setup/lyrical/README.md)：发行版、Host、FreeRTOS 和旧 Zephyr 路线。
- [micro-ROS Agent lyrical README](https://raw.githubusercontent.com/micro-ROS/micro-ROS-Agent/lyrical/README.md)：Agent 职责和 transport。
- [Zephyr 模块 README](https://raw.githubusercontent.com/micro-ROS/micro_ros_zephyr_module/main/README.md)：明确测试过的 Zephyr 版本。
- [模块 CMake](https://raw.githubusercontent.com/micro-ROS/micro_ros_zephyr_module/main/modules/libmicroros/CMakeLists.txt)、[Kconfig](https://raw.githubusercontent.com/micro-ROS/micro_ros_zephyr_module/main/modules/libmicroros/Kconfig)：静态库构建和资源参数。
- [Micro XRCE-DDS Agent 文档](https://micro-xrce-dds.docs.eprosima.com/en/latest/agent.html)：Linux PTY、Serial、网络和 Custom transport。
- [QEMU v10.2.1 mps2.c](https://raw.githubusercontent.com/qemu/qemu/v10.2.1/hw/arm/mps2.c)：UART、RAM、LAN9118 模型。

来源按调查日期读取；main 和 lyrical 分支会变化，下一阶段须重新核查并固定 commit。
