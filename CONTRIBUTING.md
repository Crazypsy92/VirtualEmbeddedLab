# 贡献指南

在 Ubuntu 24.04 或 WSL2 中按[安装指南](docs/installation.md)配置所需环境。外部贡献者可 fork 仓库，从最新 main 创建短期分支，提交 PR。先查现有 Issue，复现报告应附可复制的命令、提交 SHA 和脱敏日志。

- C11 代码沿用现有模块风格和严格编译警告。Python 入口必须有有限等待和可靠退出，保持现有 CLI 与记录格式兼容。
- 执行受影响的验收和 Core 检查。仿真报告注明后端，明确 Hardware/HIL、BLOCKED 和 NOT RUN 的边界。
- 提交说明写清改动目的。PR 附复验命令、退出码和小体积证据。生成物、虚拟环境及大日志放在 build/。
- 引入第三方代码前核对版本、授权和再分发条件，保留原始许可并更新 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
