# Peripheral capability audit

Model existence is separate from build and runtime qualification. Runtime conclusions must be read with the backend acceptance JSON. Untested models are never marked as tested.

| Peripheral | QEMU MPS2 AN385 | Renode STM32F103 | Zephyr native_sim |
|---|---|---|---|
| GPIO | FPGA IO model; not STM32 GPIO | STM32F1GPIOPort A-G model | GPIO emulator, software API |
| EXTI | No STM32 EXTI | EXTI/AFIO model and NVIC routes | Software GPIO event callbacks |
| UART | CMSDK UART previously exercised | STM32 UART model, IRQs | Native PTY UART byte channel |
| CAN | No CAN instance in AN385 | No bxCAN instance: UNSUPPORTED | CAN loopback software controller |
| SocketCAN | Host facility, not guest peripheral | Not configured | Optional native-linux-can; permission BLOCKED |
| I2C | ARM bitbang controller model, not tested here | STM32F1 I2C model, not tested | I2C emulator model, not tested |
| SPI | PL022 model, not tested here | No instance in selected platform | SPI emulator model, not tested |
| ADC | No instance in selected board | No instance in selected platform | ADC emulator model, not tested |
| DMA | No implemented DMA in selected board | STM32G0DMA reused model, not tested | DMA emulator declaration, not tested |
| PWM | No qualification | Timer alternate-function routes, not tested | No enabled PWM instance; not qualified |

Sources: [QEMU 10.2.1 mps2.c](https://raw.githubusercontent.com/qemu/qemu/v10.2.1/hw/arm/mps2.c), [Renode 1.17.0 platform](https://raw.githubusercontent.com/renode/renode/v1.17.0/platforms/cpus/stm32f103.repl), and installed Zephyr boards/native/native_sim/native_sim.dts. Source URLs and SHA256 are in evidence/stage8_1/source_audit.json.

Renode audit: Cortex-M3 plus NVIC, GPIO A-G, USART, I2C, timer, DMA and AFIO models exist. USART2 IRQ38 and EXTI10-15 IRQ40 are used by the test. Timers have their own configured model frequency; RCC is not a complete STM32 clock tree. Flash and SRAM are broad mapped memory (512 MiB and 256 MiB respectively), not valid chip capacity constraints. Model register coverage is implementation-specific and does not imply electrical fidelity or every register/bit is implemented. Selected model has no bxCAN. Blue Pill button PC13 mapping does not establish the ZET6 package pinout.

The test firmware uses a separate 64KiB/20KiB linker budget. Neither this budget nor broad Renode RAM establishes ZET6 deployability. GPIO outputs must be read back through the peripheral model, and input edges must reach actual NVIC handlers. CAN loopback tests ID/DLC/payload flow only, not arbitration, bus-off or physical bus faults. CANBusLab remains untouched for future reuse.
