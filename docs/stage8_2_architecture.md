# Stage 8.2 architecture

Independent pymodbus master process -> real PTY bytes -> existing native UART driver -> official Zephyr Modbus RTU framing/CRC -> application write preflight -> official standard function dispatcher -> device callbacks -> standard GPIO API / configuration state machine. Separate existing UART0 PTY injects GPIO input events. No shared-memory requests or same-code protocol peers are used.

Source: zephyr/apps/modbus_rtu_slave. Host: host/modbus_master. Build/cache/dependencies/raw logs: sibling modbus_stage8_2_ws. The system Python and ROS/Zephyr venvs remain unchanged; the master's system-Python venv is isolated. The existing Zephyr pip is invoked with --python targeting only this new venv when system ensurepip is absent.

Default accept_stage8_2.py runs build, full protocol/fault/effect tests, resource measurements and fresh Stage8.1 all-backend regression (including 133 historical tests). --mode build, protocol, fault or all selects scope. Only all is complete acceptance. The master owns/terminates the native process with bounded deadlines, retains exit code and every request/response trace. Protocol failures return nonzero. Historical evidence output is isolated by optional VEL_STAGE8_1_EVIDENCE; no earlier firmware/config is changed.

This is an industrial I/O software simulation. PTY has no actual 8E1 timing, RS485 transceiver delay, half-duplex collision, cable disconnect or hardware qualification. Closing/reopening the PTY verifies host connection recovery only. Modbus TCP, CAN and Stage8.3 are not implemented.
