# VirtualEmbeddedLab

VirtualEmbeddedLab 是面向嵌入式开发与教学的软件实验台。用 Host 测试和虚拟板卡学习 MCU 启动、RTOS、存储和通信总线，在没有开发板时也能复现问题、查看报文和保留验收证据。

**支持环境**为 x86_64 Ubuntu 24.04，优先面向 WSL2。桌面使用 WSLg 或 Linux X11，自动化可用 Xvfb。Windows 原生运行当前不受支持。**SIMULATED** 表示软件仿真。真实外设、板上时序和电气条件为 **Hardware NOT TESTED**。

## 快速开始

在常规 Ubuntu 用户下运行。系统安装步骤会列出 apt 命令并使用 sudo。

```bash
git clone https://github.com/Crazypsy92/VirtualEmbeddedLab.git
cd VirtualEmbeddedLab
python3 scripts/vel.py doctor
bash scripts/bootstrap_ubuntu.sh --install-system-deps --init
source build/venvs/core/vel-env.sh
python3 scripts/vel.py host
python3 scripts/vel.py arm
python3 scripts/vel.py dashboard
```

第一条 doctor 是安装前诊断，提示缺少依赖时继续执行安装步骤。GUI 中选择 **I2C → Host I2C → 启动实验 → 扫描地址**，即可观察 `0x28` 和 `0x50` 的响应。无显示器时运行 `python3 scripts/accept_i2c.py --backend host --gui skip`。

## 实验范围

| 模块 | 后端及入口 |
| --- | --- |
| Host C11 / FatFs | CMake/CTest，`python3 scripts/vel.py host` |
| Cortex-M3 / FreeRTOS | QEMU MPS2-AN385，`python3 scripts/vel.py arm` 或 `freertos` |
| 寄存器与 RTOS | GUI 的 MCU / RTOS 和高级监控，依据选定固件及后端 |
| Zephyr / Renode | [Zephyr 安装](docs/installation.md)与[仿真能力矩阵](docs/stage8_1_peripheral_support.md) |
| CAN | Zephyr API 回环与 Host 多节点模型，[CAN-H1](docs/can_loopback_inspector_report.md) · [CAN-H2](docs/can_h2_multinode_report.md) |
| Modbus RTU/TCP | 事务、分层帧、故障注入和网关，[RTU](docs/modbus_rtu_inspector_report.md) · [网关](docs/stage8_3_1_reliability_report.md) · [传输适配](docs/stage8_4_transport_abstraction_report.md) |
| Stage 8.5 I2C | Host / Zephyr 模拟控制器，寄存器、EEPROM、SCL/SDA 波形，[验收报告](docs/i2c_inspector_report.md) |
| ROS 2 / micro-ROS | 可选环境，[Stage 5 环境](docs/stage5_environment.md) · [历史 Stage 6/7](docs/stage_history.md) |

[WSLg I2C 波形](docs/evidence/i2c/i2c-waveform.png) · [CAN 多节点仲裁](docs/evidence/can_h2/arbitration.png) · [Modbus RTU 字段](docs/evidence/rtu_h2/adu.png)

## 安装与维护

- [安装指南](docs/installation.md)区分 Core、Zephyr / Stage 8 和可选 ROS 2。Host、ARM/QEMU、Host I2C 和基础 GUI 可直接使用 Core。
- [工作台架构](docs/gui_h1_architecture.md) · [历史阶段的复验资料](docs/stage_history.md) · [开源发布核查](docs/open_source_readiness_report.md) · [Core CI](https://github.com/Crazypsy92/VirtualEmbeddedLab/actions/workflows/ci.yml)。
- 历史 133 项目前 **BLOCKED**，需要匹配的 Lyrical 环境与缺失的 micro-ROS 输入。SocketCAN/vcan 另外需要相应系统权限。各阶段最新实测以验收报告为准。
- [贡献指南](CONTRIBUTING.md) · [私下报告安全问题](SECURITY.md) · [第三方许可](THIRD_PARTY_NOTICES.md) · [项目 MIT 许可](LICENSE)。
