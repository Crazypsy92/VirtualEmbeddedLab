# 第三方软件与许可

根目录 [MIT](LICENSE) 覆盖本项目原创代码。第三方代码和工具适用各自许可。构建产物是否可再分发需另按实际包含的组件核对。

| 组件与版本 | 来源及引入方式 | 许可证与位置 | 项目修改 |
| --- | --- | --- | --- |
| FatFs R0.16 + patch 1/2 | Vendored，依据恢复记录与原文件哈希，[ChaN](https://elm-chan.org/fsw/ff/00index_e.html) · [恢复来源](https://github.com/abbrev/fatfs) · [PROVENANCE](middleware/fatfs/PROVENANCE.json) | FatFs 源码自带许可，[原始许可文本](middleware/fatfs/LICENSE.txt) | 保留基线源码及已应用的两次上游补丁。工程的 diskio 与构建配置独立；原始发布 ZIP 已遗失 |
| FreeRTOS Kernel V11.2.0，`0adc196d4bd52a2d91102b525b0aafc1e14a2386` | Vendored，所用源码子集见 [PROVENANCE](os/freertos/PROVENANCE.json) · [官方 Kernel](https://github.com/FreeRTOS/FreeRTOS-Kernel/tree/0adc196d4bd52a2d91102b525b0aafc1e14a2386) | [原始 MIT](os/freertos/upstream/LICENSE.md) | 保存的源码子集有哈希。项目的移植与构建文件单独维护 |
| Zephyr 4.4.2，`dccb09599635bdff17633fa7e9dab014b91dce90` | 部署时下载，[固定源码及归档 SHA-256](zephyr/versions.json) · [上游](https://github.com/zephyrproject-rtos/zephyr/tree/dccb09599635bdff17633fa7e9dab014b91dce90) | Apache-2.0，上游根 `LICENSE`，个别文件依其 SPDX 标记 | Bootstrap 解包原始归档，实验应用位于项目树 |
| CMSIS，`512cc7e895e8491696b61f7ba8066b4a182569b8` | 安装时下载 Zephyr 模块，[官方镜像](https://github.com/zephyrproject-rtos/cmsis/tree/512cc7e895e8491696b61f7ba8066b4a182569b8) | Apache-2.0，归档 `LICENSE.txt` | Bootstrap 解包原始归档 |
| CMSIS_6，`30a859f44ef8ab4dc8f84b03ed586fd16ccf9d74` | 安装时下载 Zephyr 模块，[官方镜像](https://github.com/zephyrproject-rtos/CMSIS_6/tree/30a859f44ef8ab4dc8f84b03ed586fd16ccf9d74) | Apache-2.0，归档 `LICENSE` | Bootstrap 解包原始归档 |
| pymodbus 3.11.4 | PyPI 固定 wheel，[发布记录](https://pypi.org/project/pymodbus/3.11.4/) | BSD-3-Clause，wheel 的 `pymodbus-*.dist-info/licenses/` | 使用上游 wheel，适配代码在项目内 |
| pyserial 3.5 | PyPI 固定 wheel，[发布记录](https://pypi.org/project/pyserial/3.5/) | BSD-3-Clause，[上游 v3.5 LICENSE.txt](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt)，wheel 元数据标记 BSD | 使用上游 wheel |
| Renode 1.17.0 | 可选便携包，[下载来源和 SHA-256](simulation/renode/package.lock.json) · [官方源码](https://github.com/renode/renode/tree/v1.17.0) | Renode 主程序 MIT，源码根 `LICENSE`；附带组件依包内许可 | 使用原始发行包，实验脚本和离线平台副本由本项目生成 |
| ROS 2 Jazzy | 系统官方 apt 包，[Jazzy 发布](https://docs.ros.org/en/jazzy/Releases/Release-Jazzy-Jalisco.html)；Ubuntu 安全补丁版本随发行版 | ROS 2 是一组软件包，按各包 `package.xml`、`LICENSE` 和 Ubuntu `/usr/share/doc` 查阅 | 系统二进制未由项目修改 |
| micro-ROS / ROS 2 Lyrical 历史 Stage 6/7 | 当前 checkout 仅有应用代码和[历史拉取入口](scripts/setup_stage6_sources.py)。涉及 [micro-ROS](https://github.com/micro-ROS)、[eProsima](https://github.com/eProsima) 和 [ROS 2](https://github.com/ros2)，部分参考版本见脚本 | **BLOCKED**。历史依赖锁未恢复，实际 commit、全部原始许可文件及曾有的补丁无法逐项重建。完整历史二进制或第三方源码包发布前需补齐核查 | 历史下游改动未完整核验 |
| Ubuntu 工具链 | 通过 Ubuntu apt 获取 GCC、GDB、QEMU、CMake、Ninja、Python、Tk、DTC 与可选 Xvfb。补丁版本由 Ubuntu 维护 | 各包 `/usr/share/doc/<package>/copyright`；作为系统工具安装 | 未修改、未 vendored |

## Zephyr Python 构建链

[安装锁](zephyr/requirements-lock.txt)与[构建锁](zephyr/requirements-build-lock.txt)逐项记录实际版本和文件 SHA-256。以下依赖从对应的 PyPI 官方发行项目取得，保留发行归档自带的许可文件。项目未修改这些依赖。

| 依赖 | 发行源及许可位置 |
| --- | --- |
| Jinja2、MarkupSafe | [Jinja2](https://pypi.org/project/Jinja2/) · [MarkupSafe](https://pypi.org/project/MarkupSafe/)，BSD-3-Clause，包内 LICENSE |
| PyYAML | [PyYAML](https://pypi.org/project/PyYAML/)，MIT，包内 LICENSE |
| anytree | [anytree](https://pypi.org/project/anytree/)，Apache-2.0，包内 LICENSE |
| colorama | [colorama](https://pypi.org/project/colorama/)，BSD-3-Clause，包内 LICENSE |
| docopt | [docopt](https://pypi.org/project/docopt/)，MIT，源码归档 LICENSE |
| intelhex | [intelhex](https://pypi.org/project/intelhex/)，BSD-3-Clause，包内 LICENSE |
| packaging | [packaging](https://pypi.org/project/packaging/)，Apache-2.0 或 BSD-2-Clause，包内许可证 |
| pyelftools | [pyelftools](https://pypi.org/project/pyelftools/)，上游 public-domain 声明及保留的个别代码 BSD / MIT 条款，包内 LICENSE |
| pykwalify | [pykwalify](https://pypi.org/project/pykwalify/)，MIT，包内 LICENSE |
| python-dateutil、ruamel.yaml | [python-dateutil](https://pypi.org/project/python-dateutil/)（BSD-3-Clause）和 [ruamel.yaml](https://pypi.org/project/ruamel.yaml/)（MIT），包内 LICENSE |
| tzdata | [tzdata](https://pypi.org/project/tzdata/)，Python 打包 Apache-2.0 与 IANA 数据声明，包内 LICENSE / LICENSE-APACHE |
| west | [west](https://pypi.org/project/west/)，Apache-2.0，包内 LICENSE |
| setuptools、wheel | [setuptools](https://pypi.org/project/setuptools/) 和 [wheel](https://pypi.org/project/wheel/)，MIT，包内 LICENSE |
| jsonschema、jsonschema-specifications、referencing、attrs、rpds-py | [jsonschema](https://pypi.org/project/jsonschema/)、[specifications](https://pypi.org/project/jsonschema-specifications/)、[referencing](https://pypi.org/project/referencing/)、[attrs](https://pypi.org/project/attrs/)、[rpds-py](https://pypi.org/project/rpds-py/) 均为 MIT，包内许可证 |
