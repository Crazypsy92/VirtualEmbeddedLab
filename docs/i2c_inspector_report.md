# Stage 8.5 I2C 实验台验收

基线 `ff8853cd3892464c59bcd694bab091511e1cccee`，WSL2 Ubuntu 24.04，工作台运行于 WSLg。两种后端均标记 **SIMULATED**，实体器件、逻辑分析仪和硬件在环均为 **Hardware NOT TESTED**。需求见 [Issue #12](https://github.com/Crazypsy92/VirtualEmbeddedLab/issues/12)。

## 软件验收

| 检查 | 结果 | 实际记录 |
| --- | --- | --- |
| Host 与 Zephyr 模型 | PASS 6/6 + 6/6 | 两种后端各扫描 112 个地址，0x28 与 0x50 应答，110 个不存在地址返回 NACK |
| 批量读写 | PASS | 每个后端 1,000 笔连续编号，500 笔写后读回，数据逐笔核对 |
| Repeated START 与 SCL/SDA | PASS | 每个后端 120 笔，逐事件和逐半周期核对边沿、MSB、读写位以及第 9 个时钟。实测模型周期分别为 10 µs 与 2.5 µs |
| EEPROM | PASS | 页内回卷、写周期忙 NACK、随机读、顺序读以及首尾回卷 |
| 故障及恢复 | PASS | 6 类总线/设备异常，8 条非法输入无发帧记录。每个后端连续 100 笔恢复 |
| Headless / WSLg | PASS 1/1 + 1/1 | 真实窗口执行扫描、寄存器写读、EEPROM 随机读、波形、导出及停止。最终命令退出后无所属子进程，GUI 锁已释放 |

回归通过 Host CTest 20/20、Stage 8.4 传输 7/7、RTU 双后端流程 2/2、Stage 8.2 RTU 3/3（1,026 笔）、Stage 8.3 网关 7/7（含独立一致性检查）、CAN-H1 6/6、CAN-H2 7/7、GUI-H1 7/7、Stage 8.1 native_sim 4/4。首轮并行冷构建有部分回归超时，最终结果来自逐组复跑。

历史 133 项为 **BLOCKED**，当前是 ROS 2 Jazzy，Stage 7 需要 Lyrical 和缺失的 micro-ROS 输入。当前 WSL 缺少 CAP_NET_ADMIN，SocketCAN/vcan 检查为 **BLOCKED**。详见[门禁日志](evidence/i2c/historical-preflight.log)和[机器摘要](evidence/i2c/summary.json)。

## 后端与证据

- **Zephyr I2C** 使用工程固定的 Zephyr 4.4.2、`native_sim/native/64` 和开发板已有的 `zephyr,i2c-emul-controller`。独立 C 应用注册两个目标，按速率调用 `i2c_configure`、`i2c_get_config` 和 `i2c_transfer`。桥接回调上报真实地址、消息数量、标志、写字节和读长度，Python 将这些字段与请求核对，再执行共用设备模型。读回内容和退出码再由 Zephyr 返回并核对。缺失地址由 Zephyr controller 直接返回 `-EIO`，无需触发设备回调。参见 [Zephyr native_sim 文档](https://docs.zephyrproject.org/latest/boards/native/native_sim/doc/index.html)。
- **Host I2C** 使用相同设备状态和事件模型，运行时只需 Python 标准库。工作台允许显式选择该后端。
- **总线事件和时序** 由执行事务的模型生成。JSONL 同时记录原始请求、交流结果、总线事件、每个 SCL/SDA 电平样本和 Zephyr 证据（如适用）。GUI 从捕获的九位序列解出字段，波形直接绘制后端采样。Zephyr 模拟控制器提供消息级证据，位级时序由项目模型提供。

| 模型 | 7-bit 地址 | 储存与行为 |
| --- | --- | --- |
| 通用寄存器 | `0x28` | 256 字节，初始为 0，1–32 字节访问。单字节寄存器索引，越界拒绝 |
| 24C02 类 EEPROM | `0x50` | 256 字节，初始为 `FF`，8 字节页，最长 8 字节页写。跨页写在原页内回卷，顺序读指针在末尾回到 0。成功页写在 STOP 后进入固定 5 ms 仿真写周期，忙时地址 NACK |

EEPROM 模型依据 24LC02B 的页内写入和 ACK 轮询行为选择参数，设备地址固定为 `0x50`。写周期属于仿真时钟，等待现实时间不会推进它。可连续探测、在批量操作之间设定微秒间隔，或点击「推进仿真 5 ms」。设备内容随会话结束释放。参见 [Microchip 24LC02B 数据手册](https://ww1.microchip.com/downloads/en/DeviceDoc/21709D.pdf)。

## 操作与时序

1. 在 WSLg 从仓库根目录运行 `python3 scripts/vel.py dashboard`，选择 **I2C → Zephyr I2C** 或 **Host I2C**，点击「启动实验」。首次 Zephyr 会话会先构建模拟器。连接后显示实际 backend 与设备配置。
2. 选择 100 或 400 kHz，点击「扫描地址」检查 `0x08–0x77`。逐地址 ACK/NACK 都进记录。也可填写具体 HEX 地址、偏移、长度与 DATA，使用「单次发送」或「批量发送」。批量会执行当前操作 1–100 次。
3. 选中历史事务，在「字节 / 字段」中查看地址的 7 位、读写位、线上字节、数据与第 9 个时钟的 ACK/NACK。选中字节后切到「SCL / SDA 时序」，可查看完整事务或取消「完整事务」只看该字节。
4. 「清空显示」保留本次原始记录。「导出 JSONL」保存会话记录到指定位置。「停止当前任务」结束会话并释放工作进程。

随机读按 `START → Address W → Pointer → Repeated START → Address R → Data → STOP` 执行。地址和写入数据由设备确认。读出的前序字节由主机 ACK，末字节由主机 NACK，以结束读取。地址和数据按 MSB first 传送，读写位在地址字节最低位。START 和 Repeated START 在 SCL 高电平时使 SDA 从高到低，STOP 使其从低到高。模型采用理想方波，100 kHz 周期 10 µs，400 kHz 周期 2.5 µs，每个字节包含 8 位和第 9 个应答周期。物理 I2C 的标准时序和电气要求见 [NXP UM10204](https://www.nxp.com/docs/en/user-guide/UM10204.pdf)。

## 故障与限制

| 情况 | 证据和处理 |
| --- | --- |
| 缺失地址 / EEPROM 忙 | 地址字节后的设备 NACK，记录原因并发出 STOP |
| 选错设备模型 | 实际设备 ACK 地址，随后实验操作因模型不匹配中止并发出 STOP |
| 指定写字节拒收 / 主机终止 | 写字节索引从指针 0 开始，记录该字节的第 9 位与 STOP。故障事务的写入在模型中整笔丢弃 |
| Busy / Timeout | 模拟 SDA 保持低，未发送 START。Timeout 推进 25 ms 仿真时间。这两类注入在模型层处理 |
| 非法 HEX 地址 / 空 DATA / 长度 / 越界 | 发出前拒绝。原始事务 JSONL 无相应发帧记录 |

模型为单主机，使用理想电平和仿真时间。上升时间、开漏引脚行为、时钟拉伸、多主机仲裁和硬件电气性能超出本轮验收。I2C 字段视图包含 I2C 本身的地址、数据和应答。

## 复验

```sh
python3 scripts/accept_i2c.py --gui required
python3 scripts/accept_i2c.py --backend host --gui skip
```

完整验收使用工程已有的 Zephyr 构建依赖和 Tk。截图需要 WSLg 与 ImageMagick `import`。默认原始输出为 `build/workspaces/i2c-acceptance/run-*/`，也可指定 `--output`。当 `--gui required` 生效时，WSLg 未通过会返回非零退出码。精简证据见[机器摘要](evidence/i2c/summary.json)、[校验索引](evidence/i2c/sha256.json)及[完整波形](evidence/i2c/i2c-waveform.png)。

回归使用以下命令。原有 Stage 7 门禁单独运行，便于区分环境缺失与本阶段的可执行测试。

```sh
python3 scripts/vel.py host
export PYTHONPATH="${VEL_PYTHON_PACKAGES:-$PWD/build/recovery-zephyr/python}${PYTHONPATH:+:$PYTHONPATH}"
python3 tests/host/test_transports.py
python3 tests/gui/test_rtu_transport.py Protocols
python3 tests/gui/test_gui_h1.py
python3 tests/gui/test_can_inspector.py
python3 tests/gui/test_can_bus.py
python3 scripts/accept_stage8_2.py --mode protocol
python3 scripts/accept_stage8_3.py --mode all
python3 scripts/accept_stage8_1.py --backend native_sim
python3 scripts/accept_stage7.py
```

## 后续 STM32 接入

保持 7-bit 地址和写段/读段契约。在 Zephyr 为 STM32 配置真实控制器后，可沿用 `i2c_transfer` 和读写缓冲区。使用其他 SDK 时核对地址 API 要求是否左移，并保留组合写读的 Repeated START。板上先确认 SCL/SDA 引脚复用、电压、开漏与上拉，再用独立逻辑分析仪或控制器捕获验证实际周期、ACK/NACK 和边界。实际捕获应单独标记 Hardware/HIL。
