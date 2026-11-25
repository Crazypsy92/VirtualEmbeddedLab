# 开源发布核查

[Issue #13](https://github.com/Crazypsy92/VirtualEmbeddedLab/issues/13) 的开发基线为 `60900bff4a05109c4f36f24514e81627fd5818a7`。干净 CI 实测提交为 `2132034f512ea035f98341d836dbf52775bc71dc`。支持平台为 x86_64 Ubuntu 24.04 和 WSL2 Ubuntu 24.04。

## 干净环境验收

GitHub Actions 使用两个独立的全新 Ubuntu 24.04.5 x86_64 runner，从 GitHub checkout 开始。两项均重新安装所需 apt 依赖和独立 venv。Zephyr job 从固定提交归档下载源码并验证 SHA-256。运行中没有配置依赖或构建缓存恢复。[Core 与 Zephyr 工作流实测](https://github.com/Crazypsy92/VirtualEmbeddedLab/actions/runs/45583473528)

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Core bootstrap 和 doctor | PASS | [Core 日志摘录](evidence/open_source/ci-core-excerpt.log) |
| Host Debug、Release、ASan/UBSan | PASS，各 20/20 | 同上，三组独立 CTest |
| ARM Cortex-M3 / QEMU / GDB | PASS，6/6 | 同上 |
| Host I2C + headless worker | PASS，7/7 | 同上 |
| Xvfb GUI 和 supervisor | PASS，窗口 1/1、事件与生命周期 5/5 | 同上 |
| Zephyr 固定源码、venv、doctor | PASS | [Zephyr 日志摘录](evidence/open_source/ci-zephyr-excerpt.log) |
| I2C Zephyr / native_sim | PASS，6/6 与 4/4 | 同上 |
| ROS 2 Jazzy / Stage 5 基础通讯 | PASS（独立 WSL 测试） | 系统 Python 的 rclpy、话题收发和服务返回值 42，子进程已回收。[机器摘要](evidence/open_source/summary.json) |
| ROS 2 Lyrical / Stage 6–7 历史 133 项 | BLOCKED | Lyrical 默认 apt 平台为 Ubuntu 26.04，当前 WSL 使用 Jazzy。三个历史 micro-ROS 锁/构建输入仍缺失。[历史门禁日志](evidence/i2c/historical-preflight.log) |
| SocketCAN/vcan | BLOCKED | 无 CAP_NET_ADMIN 的历史 native_sim 门禁记录，详见 Zephyr 日志 |
| WSLg 完整界面与 Hardware/HIL | 本轮完整 WSLg 回归 NOT RUN，Hardware NOT TESTED | CI GUI 使用 Xvfb。既有 [Stage 8.5 WSLg 截图和报告](i2c_inspector_report.md)继续保留 |

Core 和 Zephyr 按[安装指南](installation.md)复验。Core 是 PR 的独立验收路径，Zephyr 在主分支或手动运行。完整历史阶段以及 ROS 2 依赖由单独环境管理。CI artifacts 的 ID、SHA-256 和到期时间见[日志索引](evidence/open_source/summary.json)。仓库保留[摘录及校验值](evidence/open_source/sha256.json)。

## 许可与仓库卫生

| 发布前核查 | 结果 | 证据 |
| --- | --- | --- |
| 首页与安装文档、截图入口 | PASS | [README](../README.md) · [安装指南](installation.md) |
| 原阶段资料与报告 | PASS | [历史资料](stage_history.md)，原报告和证据继续保留 |
| 协作、安全报告与模板 | PASS | [贡献入口](../CONTRIBUTING.md) · [安全报告入口](../SECURITY.md) · [模板](../.github) |
| 已分发的第三方源码、依赖版本和许可 | PASS | FatFs 5/5、FreeRTOS 30/30 个文件匹配已有来源哈希。下载依赖及许可见[第三方声明](../THIRD_PARTY_NOTICES.md) |
| 历史 micro-ROS 构建产物再分发核查 | BLOCKED | 原始依赖锁未恢复，整套历史二进制及源码包的许可清单无法确认 |
| 当前工作树构建产物、缓存、虚拟环境、体积 | PASS（规则扫描） | 已跟踪内容未检出 build 路径、虚拟环境或 ELF/对象文件等。最大 blob 为 361,476 字节。见[机器摘要](evidence/open_source/summary.json) |
| 当前工作树常见凭据格式 | PASS（规则扫描） | GitHub 令牌、AWS Access Key 与私钥头的正则扫描为零。该检查覆盖常见格式 |
| 历史日志中保留的机器路径 | BLOCKED（公开范围复核） | 17 个已发布文档和证据文件命中绝对路径规则。从发布包选取这些证据前，应确认账户和目录路径可公开。原证据保留以维护现有哈希与追溯关系 |

发布候选只涵盖源码及已说明的可复验实验。正式 Release、Tag 和仓库设置由维护者验收后决定。
