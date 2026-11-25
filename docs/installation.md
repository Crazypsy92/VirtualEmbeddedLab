# 安装与首次运行

支持 x86_64 Ubuntu 24.04 与 WSL2 Ubuntu 24.04。使用系统 Python 3.12 和普通用户。WSL 建议在 Linux 文件系统下克隆工程，GUI 需要 WSLg。Ubuntu 桌面使用 X11 或 XWayland。无桌面时可在 Xvfb 下运行基础窗口检查。Windows 原生环境未纳入验收。

## Core

```bash
git clone https://github.com/Crazypsy92/VirtualEmbeddedLab.git
cd VirtualEmbeddedLab
python3 scripts/vel.py doctor
bash scripts/bootstrap_ubuntu.sh --install-system-deps --init
source build/venvs/core/vel-env.sh
python3 scripts/vel.py doctor
python3 scripts/vel.py host
python3 scripts/vel.py arm
python3 scripts/vel.py dashboard
```

Bootstrap 默认只检查。系统依赖已安装时，可只运行 `bash scripts/bootstrap_ubuntu.sh --init`。系统安装旗标显式使用 apt，Ubuntu 补丁版本由发行版维护。项目 venv 装入有版本和 SHA-256 的 Python 包。日志保存在 `build/bootstrap/`。修复日志指明的 apt、下载或哈希问题后，可重复执行相同命令。使用新终端时重新 source 当前所需 profile 的环境文件。

无桌面时可运行 Host I2C 和 supervisor 测试。若需启动 Tk 窗口，先显式安装 `sudo apt-get install --no-install-recommends xvfb xauth`。

```bash
python3 scripts/accept_i2c.py --backend host --gui skip
xvfb-run -a python3 scripts/vel.py dashboard --self-test
```

Release 和 sanitizer 可将下面的 preset 换成 `host-sanitize`。

```bash
cmake --preset host-release
cmake --build --preset host-release --parallel 4
ctest --preset host-release
```

## Zephyr / Stage 8

在同一个项目下创建独立的 Zephyr venv，固定 Zephyr 4.4.2 和 CMSIS 模块。源码版本与归档 SHA-256 见 [versions.json](../zephyr/versions.json)，Python 与构建依赖单独锁定。现有 Zephyr 工作区若提供 `VEL_ZEPHYR_BASE`，应使用固定提交或附带已校验的原始归档。

```bash
bash scripts/bootstrap_ubuntu.sh --profile zephyr --install-system-deps --init
source build/venvs/zephyr/vel-env.sh
python3 scripts/vel.py doctor --profile zephyr
python3 scripts/accept_i2c.py --backend zephyr --gui skip
python3 scripts/accept_stage8_1.py --backend native_sim
```

真实窗口 I2C 验收使用 `python3 scripts/accept_i2c.py --gui required`，额外需要 ImageMagick 的 `import`。Zephyr 源码归档下载、完整 GUI、ROS 2 以及历史 Stage 6/7 不属于基础 GitHub CI。

## ROS 2 可选环境

在独立终端使用官方二进制依赖和系统 Python。Core 引导脚本不安装 ROS。Stage 5 与 Ubuntu 24.04 的 Jazzy 配套，安装后运行 `export VEL_ROS_SETUP=/opt/ros/jazzy/setup.bash`，执行 `/usr/bin/python3 scripts/setup_stage5.py` 检查环境。该检查需要官方 ROS 消息包和 Ubuntu 的 `python3-colcon-common-extensions`。参见 [Jazzy apt 安装](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)。

Stage 6/7 的历史锁面向 Lyrical。Lyrical 官方 Ubuntu apt 平台为 26.04，复验还需要恢复原 micro-ROS 依赖锁和两个元数据文件。用独立的匹配环境核验，不替换 Core 的 Python 或 Ubuntu 24.04 的 Jazzy。参见 [Lyrical apt 安装](https://docs.ros.org/en/lyrical/Installation/Ubuntu-Install-Debs.html)。
