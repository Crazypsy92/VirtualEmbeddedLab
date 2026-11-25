# 开源发布核查

任务为 [Issue #13](https://github.com/Crazypsy92/VirtualEmbeddedLab/issues/13)，基线 `60900bff4a05109c4f36f24514e81627fd5818a7`。本页随候选提交收集[干净 Ubuntu CI](https://github.com/Crazypsy92/VirtualEmbeddedLab/actions/workflows/ci.yml)的结果。

## 当前验收边界

- 目标平台为 x86_64 Ubuntu 24.04 和 WSL2 Ubuntu 24.04。[安装指南](installation.md)包括 Core、独立 Zephyr venv 和可选 ROS 2 的入口。
- 工作台及 QEMU、I2C 等实验按软件仿真范围验收。Hardware/HIL 为 NOT TESTED。
- 历史 Stage 6/7 共 133 项需要匹配的 Lyrical 和缺失的 micro-ROS 锁与构建输入。详见[历史说明](stage_history.md)和[第三方许可](../THIRD_PARTY_NOTICES.md)。
