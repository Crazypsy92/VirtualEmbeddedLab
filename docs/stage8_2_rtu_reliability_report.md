# Stage 8.2-R1 Modbus RTU 可靠性复验

2026-11-24，Issue #3。基线为 main 的 **4fa470ac3df4b8459fca2dc8eccb13aad70c7ef9**。独立工作树使用 WSL2 Ubuntu 24.04.5、普通用户 bridge、x86_64。Zephyr 4.4.2 源码固定在 **dccb09599635bdff17633fa7e9dab014b91dce90**，目标为 native_sim/native/64。测试使用 GCC 13.3.0、CMake 3.28.3、Ninja 1.11.1、Python 3.12.3、pymodbus 3.11.4 和 pyserial 3.5。环境检查识别到 QEMU 8.2.2，本轮 RTU 使用的是 native_sim。

## 原样复现

在三个全新的工作目录运行 `python3 scripts/accept_stage8_2.py --mode protocol`。从站、主站及配置均取自基线。每轮构建成功，主站以 150 ms 超时和零重试运行。主站的无响应异常均为 `pymodbus.exceptions.ModbusIOException`，从站在测试清理中均以 0 退出。

| 会话 | 已收到有效响应 | 失败总序号 / 压力序号 | FC / 地址 | 请求完整 ADU | 读到字节 | 退出码 |
| --- | ---: | --- | --- | --- | ---: | ---: |
| 1 | 565 | 566 / 547 | 05 / DO0 | `01050000ff008c3a` | 0 | 1 |
| 2 | 415 | 416 / 397 | 06 / HR3 | `01060003006339e3` | 0 | 1 |
| 3 | 426 | 427 / 408 | 01 / DO5 | `010100050001edcb` | 0 | 1 |

总序号包含 19 笔前置请求。原样主站只在收到帧时写响应时间，因此失败请求的精确等待耗时在原日志中不可用。短窗口保留可见报文、单调时间戳和距离上一响应的间隔。周期统计在失败前最近一次采样，第二、三轮的最后一条周期统计分别早于失败 17、28 笔。故障定位使用新增诊断中的即时统计与实际 PTY 收发。

## 受控诊断

以下会话均为 250 × 4 笔压力序列。表中的间隔是前一笔主站调用结束到下一笔调用开始的实际中位数。每项使用独立进程、PTY 与日志，零重试。基线固件上的第四、五行只是切换主站收发方式。第六行启用 RX-ready 但保留原 pymodbus 等待实现，用于区分两类故障。

| 参数 | 完成数 / 计划 | 实际间隔中位数 | 结果 |
| --- | ---: | ---: | --- |
| pymodbus / 150 ms / 额外间隔 0 | 1000 / 1000 | 0.085 ms | 一次通过，原样三轮仍有失败 |
| 仅超时改为 600 ms | 985 / 1000 | 0.092 ms | 第 986 笔主站提前返回，之后读到正确响应 |
| 仅请求间额外等待 20 ms | 1000 / 1000 | 20.292 ms | 一次通过，样本不足以认定有效，更早 GUI-H1 诊断中仍见失败 |
| raw serial / 150 ms / 额外间隔 0 | 312 / 1000 | 0.116 ms | 第 313 笔从站读到请求，未写出响应 |
| raw serial，另一次并记录 read 请求长度 | 174 / 1000 | 0.205 ms | 第 175 笔被 RX 清理路径读走 |
| RX-ready + 原 pymodbus 实时时钟 | 748 / 1000 | 0.213 ms | 第 749 笔主站提前返回，之后读到正确响应 |

### 从站接收切换时清理了下一帧

raw 第 175 笔 `01050003ff007c3a` CRC 有效。上一帧响应已由从站写入 PTY，主站随后发送请求。约 1.09 ms 后（距本次主站写入完成约 0.10 ms），从站以长度参数 **8** 调用读取并取走全部 8 字节，后续未写出该请求的响应。native_sim 正常接收先从 PTY 预读 1 字节，再由 RTU 以剩余缓冲区长度读取，窗口中观察到长度参数 **255**。失败读的地址可解析为 `nsi_host_read` → `np_uart_read_n`，配合 Zephyr `subsys/modbus/modbus_serial.c` 的固定 8 字节 FIFO drain 与项目配置，确认失败发生在 RX 禁用期间的清理路径。IRQ 路径的两个 drain 调用点都会在 RX 尚未开启时丢弃数据，本次抓包未区分具体是哪一个调用点。

native_sim UART 的 TX FIFO 写入直接将字节交付给宿主 PTY，宿主可以在从站完成 TX 后处理之前读到回应。Zephyr ISR 在切回接收前清理 RX FIFO 以丢弃本地回显，PTY 上提前到达的后继请求落入该窗口。独立 raw 路径复现说明此丢帧发生在 pymodbus 解析之前。

### 主站的实时时钟跳变提前结束等待

打开 RX-ready 后，第 749 笔 `0106000300bb39b9` 送出。pymodbus 以 `time.time()` 计算接收截止时间，该请求发送后约 **7.5 ms** 即调用了 `read(0)`，得到空结果。等待期间 CLOCK_REALTIME 相对于 CLOCK_MONOTONIC 向前跳变约 **843.7 ms**。从站正常地预读 1 字节并读完剩余请求，在发送后约 **30.2 ms** 写出 CRC 正确的完整回包，主站诊断随后实际读到了它。600 ms 的对照同样观测到提前返回及迟到字节，未为那一次采集时钟偏移，故不单独对其归因。

`responses` 和 IR4 的含义是已准备响应。只有真实 PTY 上的写入与主站实际读取匹配，才记为成功。

## 修复与边界

- native_sim 从站在既有 UART0 控制通道接受 `R` 探测。对单个在途请求，下一笔发送前主站等待一个 `R` 应答。从站主线程在 DE=0、RE=1 后发布应答，高优先级 UART 回调已完成清理并重新启用 RX。UART1 继续只承载 Modbus RTU。控制探测独立采用 150 ms 上限，失败时显式退出，尚未发送的事务不会被重发。
- Stage 8.2 测试主站沿用 pymodbus 的收发、轮询策略、帧解析和响应验证，只将 PTY 等待循环的截止时间改为单调时钟。RTU 超时仍为 150 ms，零重试，也没有新增固定请求间隔。Stage 8.3 网关、GUI-H1 源码、寄存器表和 Modbus 功能码均未修改。
- 软件从站配置为 115200 8E1。PTY 主站使用 parity=N 验证字节流。Hardware、物理 RS485 和 Ethernet 均为 **NOT TESTED**，Stage 0–7 历史 133 项和 Stage 8.3.1 耐久均为 **NOT RUN**。

## 正式验收

正式批次重新构建固件，按顺序启动五个相互独立的从站进程和 PTY。每轮执行原压力序列并保留前置和收尾检查，共 1,026 笔正常请求。审计工具比较主站传入解析器的实际字节与从站 PTY 系统调用记录，逐笔检查顺序、请求和只有一个响应、CRC、从站地址、功能码、压力响应内容和 150 ms 内的到达时间。每轮计数均为 requests=valid=responses-prepared=1026，errors=crc=exceptions=0。

| 项目 | 结果 |
| --- | --- |
| 轮 1 | PASS，1,000 对，最大响应耗时 45.75 ms |
| 轮 2 | PASS，1,000 对，最大响应耗时 43.45 ms |
| 轮 3 | PASS，1,000 对，最大响应耗时 34.56 ms |
| 轮 4 | PASS，1,000 对，最大响应耗时 47.19 ms |
| 轮 5 | PASS，1,000 对，最大响应耗时 50.99 ms |
| Stage 8.2 fault | 3/3，包含非法请求、异常响应、写入原子性和重新打开 PTY |
| GUI-H1 | WSLg 7/7。FC05 驱动 DO0 0→1→0，FC01 和 IR7 一致。DI=0101 经 FC02 和 IR6 确认。关闭后确认从站、Supervisor、受管 Worker 和两条 PTY 均已退出或释放 |
| Stage 8.3 Gateway | 7/7，含 6 个网关测试组和独立 RTU 状态一致性组 |

五轮共审计 **5,000 对压力报文，5,130 对正常报文**。空帧、部分帧、CRC 错误、迟到、错配和重复响应均为 0。

早期双修复批次保留了一次**发送前**控制通道超时。当时已有 1,018 对 RTU 报文，下一笔尚未发送，未观察到该笔的 RTU 空响应。具体停顿原因未定位。该批次其余四轮完整通过，独立正式批次在相同修复和控制上限下五轮完整通过。第一次 GUI 检查的 DO/DI 操作已完成，但日志页更新断言失败，另外两个 ARM 测试缺少构建产物。正式 GUI 回归使用逐文件校验过 GitHub blob 的 Draft PR #2 副本（`85b1eb4363ba78ef67b6aba9f85691f3c19d693b`），只叠加本次从站改动，并放入原有 ARM/Zephyr 测试 ELF 后 7/7。第一次失败日志也收录于清单。

## 复跑与证据

在 WSL 普通用户环境，从工程根目录执行。若依赖在工程目录之外，按现有 `vel_env.py` 约定设置 `VEL_ZEPHYR_BASE`、`VEL_TOOLS_ROOT`、`VEL_PYTHON_PACKAGES`。

```bash
python3 scripts/retest_stage8_2_rtu.py build/rtu-r1/replay
python3 scripts/diagnose_stage8_2.py \
  build/rtu-r1/replay/work/modbus_stage8_2_ws/build/zephyr/zephyr.exe \
  build/rtu-r1/diag-replay --ready --monotonic
VEL_WORK_ROOT="$PWD/build/rtu-r1/gateway-replay" \
  python3 scripts/accept_stage8_3.py --mode all
```

对照诊断可以对基线 ELF 单独使用 `--timeout .6`、`--gap-ms 20` 或 `--transport raw`。诊断在首个失败停止主动发请求，然后采集原始字节和即时状态。正式固件的 ELF SHA-256 为 `a006e6dcbade6fc7965195698badc6a6772b132a2375af283fa670d042b26a15`。

- 版本、固件 SHA、源码 SHA、命令、对照参数和各轮计数。[机器摘要](evidence/stage8_2_rtu_reliability/summary.json)
- 原始三轮的最后 11 笔事务。[基线短窗口](evidence/stage8_2_rtu_reliability/baseline-windows.json)
- 失败前十笔、失败帧、失败后的 PTY/状态采样。[FIFO 清理窗口](evidence/stage8_2_rtu_reliability/fifo-1-window.json) · [实时时钟跳变窗口](evidence/stage8_2_rtu_reliability/ready-trace-1-window.json)
- 早期发送前失败及正式 GUI 的可核对报文。[控制超时窗口](evidence/stage8_2_rtu_reliability/pre-transmit-failure-window.json) · [WSLg 回归](evidence/stage8_2_rtu_reliability/gui-regression.json)
- 完整日志保留在工作树的 `build/rtu-r1/` 下，清单记录仓库相对路径、大小和 SHA-256。[原始日志清单](evidence/stage8_2_rtu_reliability/log-manifest.json)
