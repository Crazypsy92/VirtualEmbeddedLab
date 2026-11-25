# VirtualEmbeddedLab

一个纯软件的虚拟嵌入式实验室：在 QEMU / Zephyr `native_sim` / Renode 上运行 Cortex-M3 固件（裸机 / FreeRTOS / Zephyr），端到端验证虚拟传感器、micro-ROS、Modbus RTU/TCP 网关，并内置故障注入、性能测量与回归验收流水线。全程不依赖真实硬件（`Hardware: NOT TESTED`）。

> **License**: MIT — 见 [LICENSE](LICENSE)。FatFs、FreeRTOS 等第三方组件保留各自许可，详见各子目录。
>
> 历史恢复与迁移记录：[恢复记录](docs/recovery_2026-11-21.md) · [迁移报告](docs/recovery_migration_report.md)。
>
> **文档与证据说明**：部分历史 stage 报告与验收证据（`evidence/`）未随仓库分发，可由对应 `scripts/accept_stageX.py` 在本地重新生成；文中标注"未随仓库分发"者即属此类。

## 快速开始

在 WSL Ubuntu 中进入工程根目录后，可运行以下命令进行构建与测试：

```bash
cd <repo>
python3 scripts/vel.py doctor
python3 scripts/vel.py host
python3 scripts/vel.py arm
python3 scripts/vel.py freertos
python3 scripts/vel.py zephyr
python3 scripts/vel.py ros
python3 scripts/vel.py gateway --mode all
python3 scripts/vel.py reliability --mode quick
```

图形实验入口为 `python3 scripts/vel.py dashboard`（WSLg + Tkinter）。Modbus RTU 的「RTU 协议检查」页支持 FC01/02/03/04/05/06/0F/10，可查看实际 TX/RX、逐字节字段、CRC 和写后回读。日志页保留本次会话记录。[Stage 8.2-R2 使用与验收](docs/modbus_rtu_inspector_report.md)。展开「故障注入」可查看实际修改字节、异常响应及后续 FC03 的恢复结果。[RTU-H3 使用与验收](docs/rtu_h3_fault_injection_report.md)

CAN 提供标准帧、扩展帧交互发送与 IDE 过滤，保留原 Loopback 自检，并可用 [多节点总线模式](docs/can_h2_multinode_report.md) 观察软件仲裁与错误恢复。[CAN-H1 使用与验收](docs/can_loopback_inspector_report.md) 未恢复的 micro-ROS 环境显示不可执行。运行 `python3 scripts/vel.py dashboard --advanced` 查看寄存器，或加 `--live` 启动实时 FreeRTOS 监控。

验收入口为 python3 scripts/accept_gui_h1.py。更多信息见 [功能范围](docs/gui_h1_capabilities.md) 和 [验收报告](docs/gui_h1_report.md)。没有 WSLg 时可加 --headless 执行注册表和作业生命周期检查。

网关在启动时会显示当前步骤及日志位置。如果此前终端用 Ctrl+Z 挂起了进程，回到原终端运行 jobs -l 和 fg，恢复运行，或恢复后按 Ctrl+C 停止。新版入口收到 Ctrl+Z 时会取消运行并释放工作区锁。

工具由 scripts/vel_env.py 自动定位。生成物和工作区默认写入 build，外部安装可用 VEL_TOOLS_ROOT、VEL_ZEPHYR_BASE、VEL_PYTHON_PACKAGES、VEL_ROS_SETUP 或 VEL_WORK_ROOT 指定。当前环境需已安装 ROS 2 Jazzy；Stage 6/7 的 micro-ROS 依赖锁和对应环境是运行该部分的前置条件。

网关的 --mode all 执行本机网关验收。要运行完整的历史回归链，另加 --historical。专项 quick 包括相同 TID、迟到 RTU 响应、TCP 字节流和 100 轮恢复。stress 和 endurance 分别运行 10,000 次和真实 30 分钟专项。


已实现 Stage 0 至 Stage 6：WSL2 Ubuntu、Host C11、Cortex-M3 / QEMU mps2-an385。无真实硬件操作；Stage 2 使用官方 FatFs，Stage 3 在 QEMU Cortex-M3 上运行官方 FreeRTOS 与多任务 FatFs。

当前最新 Stage 6：真实 micro-ROS Client/Agent ↔ QEMU Cortex-M3 / Zephyr4.4.2，256条采集、双向控制和故障恢复通过；15项新CTest + 108项历史回归，共123/123。最新结果见 Stage 6 报告（未随仓库分发，可由对应 stage 验收脚本生成）。下方旧阶段章节保留各自交付时的记录。

## 位置与依赖

工程根目录即本仓库，所有命令默认在此执行。生成物与工作区写入 `build/`（不提交）；外部安装路径可用 `VEL_TOOLS_ROOT`、`VEL_ZEPHYR_BASE`、`VEL_PYTHON_PACKAGES`、`VEL_ROS_SETUP` 或 `VEL_WORK_ROOT` 覆盖。

Ubuntu 需要 gcc、g++、gcc-arm-none-eabi、binutils-arm-none-eabi、cmake、ninja-build、git、qemu-system-arm、gdb-multiarch、python3。工具版本记录在各 stage 验收脚本生成的环境日志中（位于 `build/`，不随仓库分发）。

## 构建及验收

在 WSL 中运行：

```sh
cd ~/projects/stm32/VirtualEmbeddedLab
python3 scripts/build.py host
ctest --preset host-debug
python3 scripts/build.py arm
python3 scripts/run_qemu.py
python3 scripts/debug_verify.py
VEL_STAGE1_EVIDENCE="$PWD/evidence/stage2/legacy_entry" python3 scripts/accept.py --stage1-only
```

一键重新构建及执行全部验收：

```sh
python3 scripts/build.py all && python3 scripts/accept.py
```

也可直接使用 `cmake --preset host-debug` / `arm-debug`、`cmake --build --preset ...` 和 `ctest --preset ...`。两个构建目录与 CTest 测试套件彼此独立。ARM CTest 包含正常功能、QEMU 超时、异常退出、缺失输出拒绝、ELF 布局和 GDB 调试，共 6 项；原 Host smoke 独立 1 项；加入 Stage 2 后每个 Host 配置共 20 项。

产物：`build/arm/cortex_m3_demo.elf`、`.bin`、`.map`；Debug 带符号，C11 严格警告及链接警告均视为错误。`build/` 不提交 Git，验收日志提交 Git。正式验收记录与初期失败记录均保留。

## 仿真和调试

`run_qemu.py` 默认 10 秒超时，使用独立进程组，超时或失败时终止并回收自己启动的 QEMU。正常固件通过 semihosting SYS_EXIT_EXTENDED 返回退出码，UART 日志由真实 CMSDK UART MMIO 产生。脚本同时检查退出码、UART 内容和实际 Tick 递增。

`debug_verify.py` 使用仅绑定 127.0.0.1 的临时 GDB 端口，GDB 30 秒超时，退出时清理 QEMU；`gdb_verify.gdb` 是断言式批处理脚本。调试先污染 RAM，证明 Reset_Handler 的 .data 复制及 .bss 清零确实执行，再验证寄存器、单步、MSP/PSP 硬件栈、SVC、PendSV、SysTick 和最终计数。手动调试可运行：

```sh
qemu-system-arm -M mps2-an385 -cpu cortex-m3 -display none -monitor none -serial stdio -semihosting-config enable=on,target=native -kernel build/arm/cortex_m3_demo.elf -S -gdb tcp:127.0.0.1:3333
# 另一个终端：
gdb-multiarch build/arm/cortex_m3_demo.elf -ex 'target remote 127.0.0.1:3333'
```

手动调试完成后用 Ctrl-C 关闭自己启动的 QEMU；自动脚本不需人工清理。脚本必须在 WSL 执行。

## 实现与证据

[平台核对](docs/platform.md)、Stage 0（未随仓库分发，可由对应 stage 验收脚本生成）、Stage 1（未随仓库分发，可由对应 stage 验收脚本生成）。`evidence/stage0` 保存环境、Host 运行、最小 ARM 编译和板型检查；`evidence/stage1` 保存最终 Host/ARM 构建、CTest XML、UART、失败路径和 GDB 日志。

向量表在 0，代码使用 AN385 SSRAM1，数据使用 SSRAM2/3；这不是 STM32F103，也不模拟其 Flash。PSP 仅用于最小异常演示，没有实现 RTOS 调度。参见平台说明中的官方来源及 QEMU 限制。

Stage 2 已实现 Host 虚拟 SD 卡 + FatFs。FatFs on QEMU: NOT IMPLEMENTED；Hardware: NOT TESTED。后续预定 Stage 3 为 FreeRTOS + FatFs 多任务记录，本次未进入。


## Stage 2：Virtual SD Card + FatFs v1

Stage 2 验收报告（未随仓库分发，可由对应 stage 验收脚本生成） · [HAL 契约](docs/storage_design.md) · [FatFs 来源/哈希](middleware/fatfs/PROVENANCE.json) · [许可](middleware/fatfs/LICENSE.txt)

官方 FatFs R0.16 已依次应用 patch-1、patch-2。源代码已纳入仓库，正常构建无需联网；可用 `python3 scripts/verify_fatfs.py` 离线重放补丁并校验哈希，或 `python3 scripts/fetch_fatfs.py` 检查/下载固定官方输入。

从 WSL 工程根目录执行完整清洁构建、Debug / Release / ASan+UBSan / ARM CTest 和 Stage 0 回归：

```sh
python3 scripts/accept_stage2.py
```

保留的统一流程同样包括 Stage 2：

```sh
python3 scripts/build.py all
python3 scripts/accept.py
```

分别构建或测试：

```sh
python3 scripts/build.py host
python3 scripts/build.py host-release
python3 scripts/build.py host-sanitize
ctest --preset host-debug
ctest --preset host-release
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --preset host-sanitize
ctest --preset host-debug -L Stage2
ctest --preset host-debug -R '^host_smoke$'
ctest --preset arm-debug
# 独立运行原 Stage 1 验收，回归证据放在 Stage 2：
VEL_STAGE1_EVIDENCE="$PWD/evidence/stage2/legacy_entry" python3 scripts/accept.py --stage1-only
```

完整矩阵实际通过 Debug 20/20、Release 20/20、Sanitizer 20/20、ARM 6/6。每组 Host 含原 smoke 1 项、块设备 5 项、FatFs 13 项、源码补丁校验 1 项。统一入口遇到错误返回非零，构建失败也会写 FAIL；运行中状态为 IN_PROGRESS，避免沿用旧 PASS。所有新日志/CTest XML 进入 evidence/stage2；Stage 0/1 历史证据保留。

演示程序只操作指定目录内的 `sdcard.img`。新建前目录必须已存在；创建遇到已有文件会拒绝，绝不清空或格式化原镜像：

```sh
mkdir -p build/my-sd
build/host/fatfs_demo --create-new-and-format "$PWD/build/my-sd"
build/host/fatfs_demo --read-only "$PWD/build/my-sd"
# 本次已保留的演示镜像：
build/host/fatfs_demo --read-only "$PWD/build/stage2-demo"
```

默认容量 32 MiB，512 字节扇区，共 65,536 扇区。SFD FAT16，4 KiB 簇，2 份 FAT，512 个根目录项；短文件名 CP437，时间固定为 2026-01-01，无 RTC。所有测试镜像均位于 build 下的唯一临时目录；除保留演示外，测试退出后自动清理。build 和 *.img 不提交 Git。

块设备 HAL → Host 文件后端 → FatFs diskio 分层明确，FatFs 不依赖 POSIX。只读、边界、整数溢出、部分完成、短读写、读/写/sync 注入、损坏元数据、截断、目录外哨兵和跨进程恢复均有实际测试。固定随机种子为 0x5EED1234，记录 200 步序列，再由第二进程重建期望模型校验。

故障返回与数据可恢复性分开报告：注入写失败后实际观察到目标文件内容未完整恢复；sync 故障后需要取消注入并重试同步；真实 SIGKILL 测试在选定缓存写入点丢失了未同步的 123 字节。FAT 没有事务日志，不保证任意掉电时刻的完整性。本阶段仅 Host 文件模拟，没有 QEMU SD 外设、真实硬件或多任务文件系统支持。


## Stage 2：Virtual SD Card + FatFs v1

验收报告（未随仓库分发，可由对应 stage 验收脚本生成） · [HAL 契约](docs/storage_design.md) · [来源与哈希](middleware/fatfs/PROVENANCE.json) · [许可](middleware/fatfs/LICENSE.txt)

官方 FatFs R0.16 已依次应用 patch-1、patch-2。源码纳入仓库，普通构建无需网络。依赖现有 GCC、CMake、Ninja、Python3、patch 及 GCC Sanitizer 运行库，无需 sudo 挂载镜像。

完整清洁构建、Debug / Release / ASan+UBSan / ARM 测试矩阵与 Stage 0 回归：

```sh
python3 scripts/accept_stage2.py
# 统一入口目前验收至 Stage 3（单独 Stage 2 用 accept_stage2.py）：
python3 scripts/build.py all && python3 scripts/accept.py
```

各目标可独立执行：

```sh
python3 scripts/build.py host
python3 scripts/build.py host-release
python3 scripts/build.py host-sanitize
ctest --preset host-debug
ctest --preset host-release
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --preset host-sanitize
ctest --preset host-debug -L Stage2
ctest --preset host-debug -R '^host_smoke$'
ctest --preset arm-debug
VEL_STAGE1_EVIDENCE="$PWD/evidence/stage2/legacy_entry" python3 scripts/accept.py --stage1-only
python3 scripts/verify_fatfs.py
```

已实际通过 Debug 20/20、Release 20/20、Sanitizer 20/20、ARM 6/6。每组 Host 含 smoke 1、块设备 5、FatFs 13、补丁来源校验 1。新日志与 XML 位于 evidence/stage2，历史 Stage 0/1 证据保留。统一入口先写 IN_PROGRESS，失败返回非零并标记 FAIL，所有测试有限时；QEMU 与异常终止子进程会被回收。

演示只操作指定目录中的 sdcard.img。目录必须已存在；遇到已有镜像会拒绝新建，绝不自动清空或格式化：

```sh
mkdir -p build/my-sd
build/host/fatfs_demo --create-new-and-format "$PWD/build/my-sd"
build/host/fatfs_demo --read-only "$PWD/build/my-sd"
# 本次保留的镜像：
build/host/fatfs_demo --read-only "$PWD/build/stage2-demo"
```

默认 32 MiB / 512 字节 / 65,536 扇区，实际格式 FAT16 SFD、4 KiB 簇、2 份 FAT、512 根目录项。CP437 短文件名，无 RTC，时间固定 2026-01-01。测试镜像在 build 唯一临时目录下，测试后清理；build 与 *.img 均不提交 Git。

HAL、Host 后端与 diskio 分层，文件操作由官方 FatFs 完成。测试覆盖部分完成、短读写、读/写/sync 故障、只读、越界和溢出、符号/硬链接拒绝、目录外哨兵、跨进程恢复、损坏元数据和真实 SIGKILL。随机测试种子 0x5EED1234，记录 200 步，并由第二进程重建期望模型校验。

错误返回与恢复状态分别记录：写故障后目标文件未完整恢复；sync 故障需要取消注入并重试；选定缓存写入点真实 SIGKILL 后丢失未同步的 123 字节。FAT 无事务日志，不保证任意掉电时刻的完整性。Stage 2 原范围仅为 Host；当前 Stage 3 另有 QEMU ARM RAM Disk 和多任务文件系统，仍未模拟 SD 控制器或验证真实硬件。

`python3 scripts/fetch_fatfs.py` 可检查缓存或从官方地址获取固定 SHA256 输入；`verify_fatfs.py` 离线重放补丁并核对源码，不修改已纳入仓库的内核。


## Stage 3：FreeRTOS + ARM RAM Disk + 多任务记录

验收报告（未随仓库分发，可由对应 stage 验收脚本生成） · 架构（未随仓库分发，可由对应 stage 验收脚本生成） · 内存/栈统计（未随仓库分发，可由对应 stage 验收脚本生成） · [官方内核固定版本](os/freertos/PROVENANCE.json)

一键清洁构建及全部验收：

```sh
python3 scripts/accept_stage3.py
# 兼容的统一入口：
python3 scripts/build.py all && python3 scripts/accept.py
```

实际矩阵：Host Debug/Release/ASan+UBSan 各 20/20，原 ARM 6/6，新增 FreeRTOS ARM 14/14，共 80 次测试执行。历史 Stage 0/1/2 证据保留，新日志位于 evidence/stage3。单独 Stage 2 验收使用 `python3 scripts/accept.py --stage2-only`；原 Stage 1 使用现有 `--stage1-only`。

```sh
python3 scripts/build.py freertos
ctest --preset freertos-debug
ctest --preset freertos-debug -L Stage3_1
ctest --preset freertos-debug -L Stage3_2
ctest --preset freertos-debug -L Stage3_3
```

输出均在 build/freertos：freertos_cortex_m3_demo、fatfs_arm_demo、rtos_logger_0（正常）以及 rtos_logger_1..6（预期故障），每个均有 ELF/BIN/MAP；不覆盖 build/arm/cortex_m3_demo。

单独执行真实 QEMU / GDB：

```sh
python3 scripts/run_stage3.py --elf build/freertos/rtos_logger_0.elf --mode logger0
python3 scripts/gdb_stage3.py --elf build/freertos/rtos_logger_0.elf --mode logger
python3 scripts/run_stage3.py --elf build/freertos/freertos_cortex_m3_demo.elf --mode scheduler
python3 scripts/gdb_stage3.py --elf build/freertos/freertos_cortex_m3_demo.elf --mode scheduler
```

FreeRTOS V11.2.0 官方 ARM_CM3 Port 与 heap_4 固定版本，普通构建无需网络。Host FatFs 配置不变，ARM 单任务和 ARM reentrant 配置独立。新 RAM 后端复用同一 HAL，不依赖 POSIX。

RAM Disk 2 MiB，FAT12/SFD，512 字节扇区、1 KiB 簇，仅同次 QEMU 运行中保持数据。双传感器各 128 条、容量 8 的真实 Queue、Logger 独占日志、Reader 同卷另一文件、Monitor 资源监控；正常记录 256 条/5120 字节并完整重读校验。FF_FS_REENTRANT=1、FF_FS_LOCK=4，Mutex 超时 20 tick；GDB 检查官方 TCB/PSP 和实际 Mutex 持有者。磁盘延迟测试钩子用于制造合法锁争用，不是硬件时序模型。

六个故障固件分别覆盖写错、部分写错、读错、分配失败、Mutex 超时和 Queue 满，固件按预期退出 42；只有错误码、进度和停止状态正确时测试器才接受。RAM sync 不是掉电提交，不能跨 QEMU 重启持久化。本轮无真实硬件操作，未进入 Stage 4。


## Stage 4：Zephyr 与标准传感器驱动

验收报告（未随仓库分发，可由对应 stage 验收脚本生成） · 架构（未随仓库分发，可由对应 stage 验收脚本生成） · 资源（未随仓库分发，可由对应 stage 验收脚本生成） · FreeRTOS 对比（未随仓库分发，可由对应 stage 验收脚本生成） · [独立环境与操作说明](zephyr/README.md)

```sh
python3 scripts/setup_stage4.py      # 默认仅核查已固定的外部环境
python3 scripts/accept_stage4.py     # 完整 Stage 4 及历史 80 项回归
```

Zephyr v4.4.2、mps2/an385，复用现有 ARM GCC，无 SDK。外部源码、CMSIS_6、venv、局部 dtc 均在独立目录，不提交项目 Git。脚本显式使用该 venv，无需手动激活。

已完成官方示例、线程/IPC、Kconfig/Devicetree、多实例标准 Sensor API、256 条 RAM 记录、六类故障及 GDB/资源检查。新增 18/18，加上历史 80/80，共 98/98，失败 0、跳过 0。全部详细命令、日志和机器汇总在 evidence/stage4。

Stage 4 使用有界 RAM 日志，不重复移植 FatFs；不支持跨 QEMU 重启持久化。资源与 Stage 3 FatFs/RAM Disk 功能不同，对比报告不作硬件性能优劣判断。Hardware: NOT TESTED。完成后停止，未进入 Stage 5。


## Stage 5：ROS 2 + Virtual MCU Communication System

总报告（未随仓库分发，可由对应 stage 验收脚本生成） · [环境](docs/stage5_environment.md) · [架构](docs/stage5_architecture.md) · [协议](docs/stage5_protocol.md) · 资源（未随仓库分发，可由对应 stage 验收脚本生成） · [micro-ROS 评估](docs/stage5_microros_feasibility.md)

在 bridge 的 WSL Ubuntu 24.04 终端执行：

```sh
cd <repo>   # 工程根目录（克隆后的 VirtualEmbeddedLab 路径）
/usr/bin/python3 scripts/setup_stage5.py        # 检查已安装组件；不安装
/usr/bin/python3 scripts/accept_stage5.py       # 10项Stage5 CTest + 历史98项；失败返回非零
```

独立构建及关键测试：

```sh
/usr/bin/python3 scripts/stage5_host_mock_test.py   # colcon构建+明确标记的Host Mock
/usr/bin/python3 scripts/stage5_build_firmware.py   # 新Zephyr固件
/usr/bin/python3 scripts/stage5_uart_test.py
/usr/bin/python3 scripts/stage5_e2e.py
/usr/bin/python3 scripts/stage5_faults.py
/usr/bin/python3 scripts/stage5_gdb.py
```

ARM ELF/BIN/MAP位于 `build/zephyr/ros_firmware/zephyr/`。该目标复用原Sensor API驱动，业务UART1和控制台UART0分离。源码包在 `ros2/vel_ros_bridge`；colcon build/install/log/runs全部在 `build/workspaces/ros2_stage5_ws`，使用系统Python。Zephyr既有独立venv保持原位，不使用Anaconda。

手动查看完整链路（每个终端均以当前普通 WSL 用户运行，端口45671须空闲）：

```sh
# 终端1：业务通道为第2个serial，UART0仍为stdio
qemu-system-arm -M mps2-an385 -cpu cortex-m3 -display none -monitor none   -serial stdio -chardev socket,id=veluart,host=127.0.0.1,port=45671,server=on,wait=off   -serial chardev:veluart -semihosting-config enable=on,target=native   -kernel build/zephyr/ros_firmware/zephyr/zephyr.elf

# 终端2/3/4分别先设置相同环境；保证该domain没有其他实验
source /opt/ros/jazzy/setup.bash
source build/workspaces/ros2_stage5_ws/install/setup.bash
export ROS_DOMAIN_ID=171 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_LOG_DIR=build/workspaces/ros2_stage5_ws/runs/manual/ros_logs
mkdir -p build/workspaces/ros2_stage5_ws/runs/manual
# 终端2
ros2 run vel_ros_bridge bridge --port 45671 --stats build/workspaces/ros2_stage5_ws/runs/manual/bridge.json
# 终端3
ros2 run vel_ros_bridge logger --output build/workspaces/ros2_stage5_ws/runs/manual/logger.json
# 终端4：等待发布/订阅发现后执行
ros2 service call /vel/set_rate rcl_interfaces/srv/SetParameters "{parameters: [{name: period_ms, value: {type: 2, integer_value: 20}}]}"
ros2 service call /vel/start std_srvs/srv/Trigger '{}'
ros2 service call /vel/get_status std_srvs/srv/Trigger '{}'
ros2 service call /vel/stop std_srvs/srv/Trigger '{}'
```

手动链路需在固件60秒会话内操作，完成后关闭自己启动的节点。自动脚本自动选择临时端口、域和目录，并限时回收自己的进程。

ACK后才报告Service成功。四层独立统计正常均256，A/B各128；40ms慢消费者测试实测滞后并完整收取。协议使用有界COBS+CRC32。故障后进入ERROR/DISCONNECTED，需要新会话恢复。原始ROS/CTest/GDB日志和采集记录保存在外部runs目录；仓库提交摘要和哈希索引，不提交临时构建产物。

micro-ROS on Cortex-M3：**NOT INTEGRATED**；Hardware：**NOT TESTED**。本轮止于Stage5；Stage6须根据可行性报告另行决定。


## Stage 6：Real micro-ROS Client / Agent

本阶段使用真正的micro-ROS Client / Agent。新增工作区：`build/workspaces/micro_ros_stage6_ws`；不会覆盖Stage5工作区或固件。版本和源码包哈希固定在 `micro_ros/dependencies.lock.json`。

Stage6报告（未随仓库分发，可由对应 stage 验收脚本生成） · [兼容性](docs/stage6_compatibility.md) · [架构](docs/stage6_architecture.md) · 内存（未随仓库分发，可由对应 stage 验收脚本生成） · Stage5对比（未随仓库分发，可由对应 stage 验收脚本生成）

```sh
# 全部操作均在当前用户的 WSL终端中执行
cd <repo>   # 工程根目录（克隆后的 VirtualEmbeddedLab 路径）
/usr/bin/python3 scripts/accept_stage6.py
```

完整入口按顺序重建/验证Host Agent与Client、私有Newlib、ARM库、最小固件、双向Topic、GDB、固定消息、256条采集、九类故障/恢复、内存，最后执行Stage0–5全部108项回归。新测试数以实际CTest XML为准。任一步失败立即返回非零，禁止跳过关卡。

首次恢复依赖时，需要网络，只下载固定源码；后续构建/验收使用本地缓存：

```sh
/usr/bin/python3 scripts/setup_stage6_sources.py
/usr/bin/python3 scripts/stage6_build_host.py
/usr/bin/python3 scripts/stage6_host_test.py
# 只有Host关卡通过后才获取ARM依赖：
/usr/bin/python3 scripts/setup_stage6_sources.py --arm
/usr/bin/python3 scripts/stage6_build_dev.py
/usr/bin/python3 scripts/stage6_build_newlib.py
/usr/bin/python3 scripts/stage6_prepare_arm.py
/usr/bin/python3 scripts/stage6_build_arm_libs.py
/usr/bin/python3 scripts/stage6_build_firmware.py
/usr/bin/python3 scripts/stage6_arm_runtime.py
/usr/bin/python3 scripts/stage6_gdb.py
# 6.2通过后才构建6.3目标：
/usr/bin/python3 scripts/stage6_build_interfaces.py
/usr/bin/python3 scripts/stage6_build_arm_libs.py
/usr/bin/python3 scripts/stage6_build_firmware.py --acquisition
/usr/bin/python3 scripts/stage6_acquisition_test.py
/usr/bin/python3 scripts/stage6_faults.py
/usr/bin/python3 scripts/stage6_memory.py
```

Newlib4.4.0为本轮私有Cortex-M3构建，启用Zephyr要求的retargetable locking；不替换系统Newlib，不安装完整SDK。ROS/colcon用系统Python，Zephyr west用原独立venv。第三方源码与构建结果均在新工作区，原始Agent/QEMU/ROS/GDB日志也保存在其runs目录；仓库仅保存摘要及外部日志哈希索引。

最小ELF/BIN/MAP：`build/workspaces/micro_ros_stage6_ws/firmware_build/zephyr/`；采集固件对应`acquisition_build/zephyr/`。运行脚本启动本地QEMU UART1↔透明PTY字节中继↔官方Agent，UART0用于日志，自动分配临时端口和ROS域并限时回收本轮进程。没有叠加Stage5 COBS应用协议。

固定消息包`vel_micro_interfaces`版本1.0.0定义Record、Command、Ack；两路实际Sensor API采样，经Agent发布至 `/vel/micro_ros/sensor/a,b`，Host逐条检查并保存256条。Command需要匹配MCU ACK才算执行确认。错误后重新建立会话，不承诺断点续传或无限期无丢失。

本轮止于Stage6，不自动进入Stage7；Hardware仍NOT TESTED。


## Stage 7 reliability and resource acceptance

Run as the current WSL user:

```sh
cd <repo>   # 工程根目录（克隆后的 VirtualEmbeddedLab 路径）
/usr/bin/python3 scripts/accept_stage7.py
/usr/bin/python3 scripts/stage7_documents.py
```

Independent sources: zephyr/apps/recovery_firmware and micro_ros/stage7_interfaces.
Raw logs, colcon installs and baseline/optimized ELF, BIN and MAP live in the sibling micro_ros_stage7_ws. Existing fixed Stage6 dependencies must be available; no root or Conda is needed. Stage7 does not alter original Sensor drivers or earlier firmware. The only Stage6 helper change is an optional evidence directory override for isolated regression output.

The acceptance sequence runs baseline recovery/stress/fault/GDB, optimized full regression, strict resource links and all 123 historical tests. The JUnit XML determines the new test count. Failed gates stop acceptance. Each stress run validates 10000 accelerated records independently at MCU, Agent and Host. Reconnection pauses sampling until an ACKed new-session START.

See docs/stage7_architecture.md and docs/stage7_recovery_design.md（本仓库随附）；stage7_report / stage7_fault_matrix / stage7_memory / stage7_stm32_feasibility 未随仓库分发，可运行 `scripts/accept_stage7.py` 与 `scripts/stage7_documents.py` 生成。Machine evidence 位于 `evidence/`（不随仓库分发，可本地复现生成）。Resource capacity FIT does not mean an STM32 port or hardware qualification. Hardware remains NOT TESTED. Stage8 is outside scope.


## Stage 8.1 multiple simulation backends

`/usr/bin/python3 scripts/accept_stage8_1.py --backend all` runs isolated QEMU historical acceptance, native_sim and Renode. Select `qemu`, `native_sim` or `renode` for a single backend. Full QEMU regression takes substantially longer than peripheral smoke tests. Run as the current WSL user; the existing fixed Zephyr and Stage6/7 environments are required. Renode 1.17.0 portable is installed under ~/tools/renode with a pinned archive hash; no system packages or GUI are installed.

See docs/stage8_1_peripheral_support.md（本仓库随附）；stage8_1_report 未随仓库分发，可运行 `scripts/accept_stage8_1.py` 生成。Raw artifacts remain in ../simulation_stage8_1_ws. native_sim tests software GPIO/CAN emulators and real PTY bytes; Renode tests independent STM32F103 bare-metal firmware. Neither claims ZET6 hardware qualification. Optional vcan may be BLOCKED without network administration capability. CANBusLab and Stage0–7 firmware remain untouched.


## Stage 8.2 Modbus RTU industrial I/O

Run `python3 scripts/stage8_2_setup_master.py` to verify the pinned Modbus packages, then `python3 scripts/accept_stage8_2.py --mode all`. Modes build/protocol/fault select narrower checks. Zephyr v4.4.2 and native_sim/native/64 are reused; the independent master pins pymodbus 3.11.4 and pyserial 3.5. The full mode includes fresh Stage8.1 and 133 historical tests.

See docs/stage8_2_modbus_compatibility.md, docs/stage8_2_register_map.md and docs/stage8_2_architecture.md（本仓库随附）；stage8_2_report / stage8_2_memory 未随仓库分发，可运行 `scripts/accept_stage8_2.py` 生成。Native PTY does not emulate 8E1 electrical timing or physical RS485. Software direction GPIO and actual wire transcripts are recorded separately. No Modbus TCP, CAN or Stage8.3 work is included.


## Stage 8.3 Modbus TCP-to-RTU gateway

Run `/usr/bin/python3 scripts/accept_stage8_3.py --mode all`. Modes build/protocol/concurrency/fault select partial checks. The all mode validates the native_sim gateway locally. Use --historical to also request the historical chain. The local test builds an independent Zephyr native_sim gateway and the unchanged Stage8.2 slave, uses real dual PTY byte relay, then performs fresh Stage8.2/8.1 and 133 historical regressions. Reuses the existing fixed pymodbus3.11.4 venv.

The gateway binds loopback only, defaults to port15020; acceptance selects a free port at build time. Four clients, queue16, one official RTU client worker, bounded timeouts, no hidden write retries. See docs/stage8_3_compatibility.md, docs/stage8_3_architecture.md and docs/stage8_3_gateway_design.md（本仓库随附）；stage8_3_report / stage8_3_performance 未随仓库分发，可运行 `scripts/accept_stage8_3.py` 生成。Physical Ethernet/RS485 and hardware are NOT TESTED.

## Stage 8.4 Host transport

在工作台的 **Modbus → 连接 / 传输配置** 中可切换 PTY 仿真与 Serial 设备，执行真实 FC03 连接测试。无硬件复验可勾选 Serial-on-PTY。命令行 RTU 验收支持 `--transport pty` 或 `--transport serial`，TCP 主站支持 `--host`。详见[验收报告与复验命令](docs/stage8_4_transport_abstraction_report.md)。
