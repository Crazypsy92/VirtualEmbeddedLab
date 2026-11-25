# Stage 8.4 传输适配层验收

验收日期 2026-11-25。工程运行于 WSL2 Ubuntu 24.04.5，GUI 使用 WSLg。Python 3.12.3，pyserial 3.5，Pymodbus 3.11.4。基线提交 `3b2e7855aa5ef8e0c420ca2896b1188d47528a71`。需求见 [Issue #11](https://github.com/Crazypsy92/VirtualEmbeddedLab/issues/11)。

## 验收结果

| 项目 | 结果 | 实测范围 |
| --- | --- | --- |
| Transport contract | PASS 7/7 | 独立字节流与帧接口测试。短写、超时、异常关闭及重复关闭 |
| PTY | PASS | 12 笔真实 PTY 字节流往返。两套 RTU 后端共用协议测试各 1/1 |
| Serial-on-PTY | PASS | 1,000 笔双向传输，0 丢失、重复或错配。分片、读超时、断连与重连 |
| TCP Stream | PASS | 1,000 笔，0 错配。分段、粘连、半关闭、RST、拒绝连接与重连。主站另经第二个回环地址和三段 MBAP 响应验证 |
| RTU 同一协议流程 | PASS 2/2 | 两端各完成 FC03、FC06 写入回读及 6 种故障后的逐笔恢复。H3 完整测试 5/5，60 次功能故障恢复。H2 10/10，27 笔事务关联到固件事件 |
| WSLg / GUI-H1 | PASS 1/1 与 7/7 | PTY 探测与手动断开、Serial-on-PTY 探测与从站退出、不可用设备报错与锁释放 |
| CAN-H1 / H2 | PASS 6/6 与 7/7 | 1,000 帧回环，0 丢失、重复或错配。多节点、仲裁、错误恢复和 WSLg |
| Stage 8.2 | PASS（本阶段本地门） | 协议与压力在 PTY、Serial-on-PTY 各 3/3、各 1,026 笔。PTY 综合 4/4、1,031 笔，资源及终止清理通过。全链入口因历史门退出 1 |
| Stage 8.3 | PASS 7/7 | 6 项网关测试和 1 项独立一致性检查。20 次连接重建前后网关 FD 都为 7 |
| Stage 8.3.1 Quick | PASS 31/31 | 400 笔唯一 TID、12 种迟到用例、15 项 TCP 流用例、3 项恢复用例 |
| Stage 8.3.1 Stress | PASS 10,000/10,000 | 4 客户端，382.45 秒，0 超时、异常和误配。另核对 4 笔初始化写入。6 个进程与 4 个 PTY 已清理 |
| Stage 8.1 native_sim / Renode | PASS 4/4 与 3/3 | 分别独立运行。QEMU 旧回归入口需先通过 Stage 7 环境检查 |
| 独立 Host / ARM CTest | PASS 20/20 与 6/6 | Host 含 FatFs。ARM 含 QEMU 启动与异常、ELF 及 GDB |
| Stage 0–7 历史 133 项 | BLOCKED | 当前 ROS 2 为 Jazzy。Stage 7 需要 Lyrical 和三个未恢复的 micro-ROS 输入。详见[环境检查日志](evidence/stage8_4/historical-stage7-preflight.log) |
| Stage 8.3.1 Endurance | NOT RUN | 本次执行 Issue 指定的 Quick 与 Stress |
| Hardware / HIL | NOT TESTED | 实体 STM32、UART/RS-485、CAN 和以太网 |

[机器摘要](evidence/stage8_4/summary.json) · [哈希与原始日志索引](evidence/stage8_4/sha256.json) · [WSLg Serial-on-PTY](evidence/stage8_4/serial-pty.png) · [物理串口不存在](evidence/stage8_4/missing-port.png)

## 传输契约

- [ByteStreamTransport](../scripts/vel_transport.py) 负责连接、断开、设备参数与有界 I/O。一次 `read(size)` 最多返回 size 字节，读超时返回空字节，TCP EOF 和设备 I/O 错误触发断连。一次 `write(data)` 在同一期限内重试短写。写失败时前缀可能已发出，调用方应依业务语义决定如何恢复。连接由单一拥有者管理，重复关闭安全。
- 可选观测回调记录操作、backend、单调纳秒时间戳、长度、十六进制字节、错误及调用方提供的关联 ID。已有 Pymodbus RTU ADU/CRC、MBAP 分帧及 TID/Unit ID/功能码匹配沿用现有解析器。GUI 事务和网关测试分别保留原始记录。
- [FrameTransport 与 CanMessage](../scripts/vel_frame_transport.py) 定义 Classical CAN 的独立帧接口。`read_frame` 超时返回 None，断连抛 ConnectionError。每帧保留 ID、IDE、RTR、DLC、data、时间戳、通用标志和错误标志。CAN-H1 与 H2 用 façade 将已产生的 API 帧/IPC 事件转换为 CanMessage，生命周期仍由既有实验管理器管理。两者现有数据帧能力和 Host 软件时钟来源保持原有边界。

| Backend | 可配置参数及用途 | 当前验收范围 |
| --- | --- | --- |
| PTY | 串口配置、UART0 接收就绪握手 | Zephyr native_sim 从站，TX/RX、故障注入与恢复 |
| Serial | 端口、baud、数据位、校验、停止位、读写和可选字节间超时。可选 `rs485_rts` 由支持的驱动控制 | `SERIAL_BACKEND_ON_PTY` 使用真实 pyserial 打开 PTY 并执行相同协议用例。物理拔插、串口定时和驱动方向控制留待硬件机验证 |
| TCP | host/port、连接、读和写超时 | 本地 TCP 和 Zephyr Gateway。域名解析由系统处理，连接超时约束套接字连接 |
| CAN Loopback / Host Bus Model | 帧字段适配和原有实验控制 | Zephyr API 回环及多节点 Host 软件模型 |

### 后续 CAN 后端的接口映射

| 后端 | 帧字段与生命周期映射 |
| --- | --- |
| SocketCAN | 打开并绑定显式 CAN 网络接口。将 `CAN_EFF_FLAG`、`CAN_RTR_FLAG`、`CAN_ERR_FLAG` 和标识符/错误类掩码映射至 IDE、RTR、ID 和错误标志。使用内核提供的带来源时间戳或标明 Host 到达时钟。根据范围启用错误帧过滤。 |
| USB-CAN | 使用厂商 SDK 或其 SocketCAN 驱动。读取设备句柄、通道和速率，保留 SDK 的扩展帧、RTR、DLC、状态码、错误和时间来源。 |
| MCU CAN | 在驱动的收发队列边界映射 ID/IDE/RTR/DLC 及邮箱、错误和总线状态。保留设备时间基准，将目标复位、bus-off 和队列超时反馈给调用方。 |

当前 CAN-H1/H2 的真实总线接入为 Hardware NOT TESTED。vcan 未创建，当前 WSL 缺少 CAP_NET_ADMIN。参见 [Linux SocketCAN 文档](https://docs.kernel.org/networking/can.html)。

## 网关仿真稳定性

原先的 native_sim Gateway 通过 Zephyr PTY UART 的 IRQ 模拟路径收发。两次压力测试出现 Gateway 的 RTU 超时。TCP 追踪仍保留正确的 TID、Unit ID 和对应的异常功能码，Gateway 记录 `-ETIMEDOUT`，PTY relay 未记录对应 RTU 请求。实测样本见 [首次失败的 TCP 记录](evidence/stage8_4/stress-first-window.jsonl)。

Gateway 仿真配置改用 Zephyr 原生异步 UART，并将仿真内核的时钟分辨率设为 1 ms。只启用异步接口时，原来的粗粒度时钟仍使 Quick 近边界用例超时。1 ms 配置完成了原有迟到响应、隔离和恢复用例。Gateway 的服务端 RTU 超时仍为 500 ms，压力事务数量、数据、CRC、关联和失败断言保持原标准。该设置只在 Gateway 的 native_sim 构建中使用。

## 工作台与 TCP 主站

在 WSLg 执行 `python3 scripts/vel.py dashboard`，进入 **Modbus → Modbus RTU → 连接 / 传输配置**。默认 PTY 仿真。选择 **Serial 设备** 后输入可访问的端口和实际串口参数。无硬件复验时勾选 **仅用 native_sim PTY 验证 Serial**，界面会在连接后显示真实分配的 PTY 路径。配置单独保存在各次实验的 `transport-request.json`，结果文件及事务记录包含 backend、端点及状态。独立启动工作台默认仍为 PTY。

- **连接**启动 RTU 会话并读取实际状态。**测试连接**执行 FC03 读取从站 1 的 HR0。独立测试连接结束即释放端点。**断开**请求停止会话并等待资源清理。
- 物理串口打开失败会保留 Serial 和实际设备路径，界面显示系统错误。使用真实端口时禁用模拟故障与 DI 注入。实际方向信号需要外部采集。UART 8E1 教学视图按固定模型从字节推导，当前串口参数见连接配置。
- TCP 主站 `host/modbus_tcp_master/client.py [--host HOST] PORT INDEX OUTPUT` 默认使用 `127.0.0.1`。例如在已有 Gateway 监听 1502 时启动 `python3 host/modbus_tcp_master/client.py --host 127.0.0.1 1502 0 /tmp/vel-master.json`。该主站的实验包含写操作，应对具备项目寄存器映射的实验端点运行。

## 复验命令

在仓库根目录、常规 WSL 用户下运行。沿用项目的 Zephyr 工作区和 Modbus Python 依赖，可通过 `VEL_ZEPHYR_BASE`、`VEL_TOOLS_ROOT` 和 `VEL_PYTHON_PACKAGES` 指向既有工具。GUI 截图测试另需 WSLg、Tkinter 和 ImageMagick 的 `import`。

```sh
export VEL_WORK_ROOT="$PWD/build/stage84-recheck/work"
export PYTHONPATH="${VEL_PYTHON_PACKAGES:-$PWD/build/recovery-zephyr/python}${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$PWD/build/stage84-recheck"
VEL_TRANSPORT_TEST_RECORDS="$PWD/build/stage84-recheck/contracts.jsonl" \
  python3 tests/host/test_transports.py
VEL_STAGE84_SCREENSHOTS="$PWD/build/stage84-recheck" \
  python3 tests/gui/test_rtu_transport.py
python3 tests/gui/test_rtu_h2.py
python3 tests/gui/test_rtu_inspector.py
python3 tests/gui/test_rtu_h3.py Rules Native Window
python3 tests/gui/test_gui_h1.py
python3 tests/gui/test_can_inspector.py
python3 tests/gui/test_can_bus.py
python3 scripts/accept_stage8_2.py --mode protocol --transport pty
python3 scripts/accept_stage8_2.py --mode protocol --transport serial
python3 scripts/accept_stage8_2.py --mode fault
python3 scripts/accept_stage8_3.py --mode all
python3 scripts/accept_stage8_3_1.py --mode quick
python3 scripts/accept_stage8_3_1.py --mode stress
python3 scripts/accept_stage8_1.py --backend native_sim
python3 scripts/accept_stage8_1.py --backend renode
python3 scripts/vel.py host
python3 scripts/vel.py arm
```

## 真实设备接入

- Windows 串口程序使用 `COMx`。WSL 中的工作台使用 Linux 设备路径，例如 USB-UART 驱动提供的 `/dev/ttyUSB0` 或 CDC ACM 驱动提供的 `/dev/ttyACM0`。WSL2 可以通过 usbipd-win 共享并附加 USB 设备，设备出现后核对所属组和当前账户权限。设备重新枚举时优先使用可用的稳定设备链接。设备及驱动支持范围见 [Microsoft WSL USB 指南](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)。
- USB-UART 用于匹配逻辑电平的 MCU UART TX/RX 和参考地。USB-RS485 用于差分 A/B，MCU UART 与总线之间须有 RS-485 收发器。按拓扑布置总线两端终端电阻、偏置以及公共参考地或隔离，并核实适配器 A/B 极性和方向控制能力。MCU 固件实现 UART、Modbus RTU 从站、DE/RE 配合和[项目寄存器映射](stage8_2_register_map.md)。参见 [TI RS-485 设计指南](https://www.ti.com/lit/an/slla272d/slla272d.pdf)。
- 真实 CAN 需要支持目标速率的控制器、收发器和总线节点。按网络设计连接 CANH/CANL 和参考地、设置两端终端并匹配总线速率。MCU GPIO 逻辑信号通过收发器接入差分总线。参见 [TI CAN 收发器资料](https://www.ti.com/product/TCAN857-Q1)。
- 实体设备连接、USB 断开/重枚举、方向时序和电气特性分别记录为 Hardware/HIL。当前真实硬件结果均为 Hardware NOT TESTED。
