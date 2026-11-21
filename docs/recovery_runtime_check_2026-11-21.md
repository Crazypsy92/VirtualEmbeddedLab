# 恢复工程运行复测

环境为 Bridge-Ubuntu-24.04，普通用户 bridge。工具放在项目 build 下，通过环境变量仅供本次调用使用。

| 验证 | 实际结果 |
| --- | --- |
| Host Debug | 构建成功，CTest 20/20，host_smoke 直接运行成功 |
| Host Sanitizer | ASan/UBSan 构建成功，CTest 20/20 |
| FatFs demo | 真实创建并格式化虚拟镜像，重新只读打开后读回 39 字节。两次均退出 0 |
| Cortex-M3 | GCC 13.2.1 交叉编译成功，输出 ELF、BIN、MAP |
| QEMU 和 GDB | QEMU 8.2.2、GDB 15.1，CTest 6/6。UART 正常，SysTick 1→5，SVC 2 次，PendSV 1 次。检查 ELF 布局、GDB 和超时清理 |
| FreeRTOS | V11.2.0 源码校验、ARM 构建及 QEMU/GDB CTest 14/14，覆盖调度、FatFs、并发日志和故障场景 |
| Zephyr Modbus Stage 8.3 | 网关与从站在 Zephyr 4.4.2 native_sim 构建成功。现有运行用例 6/6，独立设备状态比对 1/1 |
| Stage 8.3.1 | 待验收。现有脚本仍依赖旧 Git 基线和此前的全量验收记录 |

日志位于 build/recovery-host/Testing/Temporary/LastTest.log、build/host-sanitize/Testing/Temporary/LastTest.log、build/arm/Testing/Temporary/LastTest.log 、build/freertos/Testing/Temporary/LastTest.log 和 build/recovery-arm-evidence/。

本次 ARM 和 FreeRTOS 复测使用项目内的工具目录，可在工程根目录用以下环境继续运行现有构建预设。

```bash
export PATH="$PWD/build/recovery-tools/root/usr/bin:$PATH"
export LD_LIBRARY_PATH="$PWD/build/recovery-tools/root/usr/lib/x86_64-linux-gnu"
export VEL_STAGE1_EVIDENCE="$PWD/build/recovery-arm-evidence"
export VEL_STAGE3_EVIDENCE="$PWD/build/recovery-freertos-evidence"
ctest --preset arm-debug
ctest --preset freertos-debug
```

Modbus 复测通过真实 localhost TCP Socket、双向 PTY 和两个 native_sim 进程，覆盖 8 种功能码、GPIO、TCP 分片和粘包、1,000 次混合事务、4 个客户端共 320 次事务、连接重建和下游故障处理。另做了一次独立 TCP/RTU 状态比对。运行结束后确认没有残留本次构建的仿真进程。

旧的全量验收入口仍依赖原用户、路径、Git 历史和历史验收证据。本次使用 build/recovery-zephyr/run_protocol.py 指向本地重建环境，运行原测试逻辑。初次运行外层 55 秒时限终止，清理当轮进程后用 175 秒时限重跑通过。首次日志保留在 build/recovery-zephyr/gateway/runs/protocol-y1ir2l13/。最终日志位于 build/recovery-zephyr/all-runtime.log、consistency.log 和 evidence/。本次没有执行 Stage 4–8.2 全量回归或 Stage 8.3.1 长时验收。
