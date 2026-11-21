# Stage 8.1 backend architecture

QEMU keeps AN385 Cortex-M3, RTOS and micro-ROS responsibilities. The historical acceptance runs unchanged except optional evidence output redirection. native_sim reuses the exact existing Zephyr 4.4.2 checkout and builds Linux x86_64 executables. GPIO emulator, PTY UART and CAN loopback test standard Zephyr APIs, not STM32 physical timing. Renode runs an independent ARM bare-metal ELF using the official STM32F103 platform.

All raw logs, external software archives, build trees and caches live in the sibling simulation_stage8_1_ws or ~/tools/renode. Tests run as the current WSL user. Each process group is owned and bounded by the test harness; no global kill, interface reset, WSL configuration or toolchain upgrade is performed.

Entry: python3 scripts/accept_stage8_1.py --backend all|qemu|native_sim|renode. Results remain separate; failures do not prevent other selected backends from recording their results. Backend binaries cannot be interchanged.
