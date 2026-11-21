# Platform references and decisions

Verified 2026-10-27 against the official QEMU documentation and implementation:

- https://www.qemu.org/docs/master/system/arm/mps2.html
- https://github.com/qemu/qemu/blob/master/hw/arm/mps2.c
- https://github.com/qemu/qemu/blob/master/hw/char/cmsdk-apb-uart.c
- Arm AN385: https://documentation-service.arm.com/static/5ed107a5ca06a95ce53f89e3

AN385 uses Cortex-M3. We place vectors/code in ZBT SSRAM1 at 0x00000000 (4 MiB), data/BSS in SSRAM2/3 at 0x20000000 (4 MiB). These are RAM banks; there is no STM32 Flash controller. ELF load addresses provide the data initialization image. The upper 16 KiB of SSRAM2/3 is reserved for MSP, with initial SP 0x20400000 (one past RAM). PSP has a separate aligned 1024-byte buffer. UART0 base is 0x40004000, DATA +0, STATE +4 (TXFULL bit 0), CTRL +8 (TX enable bit 0), BAUDDIV +0x10. Board clock is 25 MHz; integer baud divider is 217. SysTick uses CPU clock at 1 kHz (reload 24999).

Cortex-M architectural system registers: ICSR 0xE000ED04 (PENDSVSET bit 28), SysTick CTRL/LOAD/VAL 0xE000E010/14/18. Hardware basic frames contain R0-R3, R12, LR, PC, xPSR. EXC_RETURN 0xFFFFFFF9 returns to Thread/MSP; 0xFFFFFFFD to Thread/PSP. SVC #42 checks its actual opcode, input R0, stacked Thumb bit and frame bounds, then changes stacked R0. PendSV validates IPSR=14 and MSP return. SYS_EXIT_EXTENDED semihosting is used only to return a test exit status; UART output uses MMIO.

QEMU limits: no low-16-KiB remapping test, real timing accuracy, flash persistence, physical UART electrical behavior, or hardware validation claimed.
