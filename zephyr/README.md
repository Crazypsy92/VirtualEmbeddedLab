# VirtualEmbeddedLab Zephyr 应用

固定 Zephyr v4.4.2 / mps2/an385，外部工作区 `build/recovery-zephyr`。源码与 CMSIS_6 Commit、局部 dtc 包 SHA256 在 versions.json；venv 精确依赖在 requirements-lock.txt。Zephyr Apache-2.0，CMSIS 保留在外部官方仓库的许可。未把 upstream/SDK/venv 放进本工程。

从工程根目录执行：

```sh
python3 scripts/setup_stage4.py
python3 scripts/accept_stage4.py
```

在具有相同 Ubuntu 包源和基础 ARM GCC/QEMU 工具的全新环境，可显式执行 `python3 scripts/setup_stage4.py --install`。该脚本仅创建固定外部工作区、独立 venv，west 获取固定源码与 CMSIS_6，并局部解包 dtc；无 sudo 或系统升级。已有源码不会被覆盖或切换，版本不符会报错。PyPA bootstrap 文件若上游改变而 SHA256 不符会停止，需人工审查，不会忽略校验。

应用：apps/kernel_demo、apps/virtual_sensor_demo、apps/data_acquisition。虚拟驱动在 drivers/sensor/vel_virtual_sensor，Binding 在 dts/bindings/sensor，Overlay 在 boards/sensors.overlay。标准 Sensor API、多实例独立数据、无虚构 MMIO。

构建/运行使用 stage4_support 中的显式 venv 环境；原始 west 命令示例：

```sh
export ZEPHYR_TOOLCHAIN_VARIANT=cross-compile
export CROSS_COMPILE=/usr/bin/arm-none-eabi-
python3 scripts/setup_stage4.py
python3 scripts/vel.py zephyr
```

上面官方示例本身不自动结束，手动运行需 Ctrl-C；自动验收脚本只在捕获实际输出后受控退出。项目测试固件通过 semihosting 有限退出。

新增测试与独立 GDB：

```sh
ctest --test-dir build/zephyr-tests --output-on-failure
python3 scripts/gdb_stage4.py kernel
python3 scripts/gdb_stage4.py sensor
python3 scripts/gdb_stage4.py acquisition
python3 scripts/stage4_case.py acq0
```

测试需先由 accept_stage4.py 完成构建。18 项分别区分环境、官方示例、运行、GDB、Kconfig 禁用、必需属性缺失（预期构建拒绝）、资源；没有 native_sim 运行结果，不把编译负向用例称为 QEMU 运行通过。

产物位于 build/zephyr/*/zephyr/zephyr.elf、.bin、.map；七种集成场景在 build/zephyr/acquisition_cases。日志与 XML 在 evidence/stage4。更多说明见 docs/stage4_design.md、stage4_report.md、stage4_memory.md、stage4_rtos_comparison.md。Hardware: NOT TESTED。
