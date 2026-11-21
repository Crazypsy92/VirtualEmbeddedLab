# Stage 7 Architecture

Independent recovery_firmware and vel_recovery_interfaces reuse fixed Stage6 dependencies and original Sensor drivers. Two sensors use standard Sensor API, RCL/RCLC, RMW/XRCE, IRQ UART1, TCP/PTY relay, Agent and independent ROS logger. UART0 carries diagnostics. Topics: /vel/recovery/a, b, command and status.

Records identify boot, session, sensor, sequence and physical sample index. Logger checks temperatures and continuity. Agent forwarding counts use real DDS DataWriter payloads, compared with ROS records. Publish success alone is not confirmed delivery.

Builds and raw logs live in ../micro_ros_stage7_ws. Committed JSON records paths, commands and hashes. accept_stage7.py runs ordered CTest groups and historical acceptance as the current WSL user. Original firmware and evidence remain protected.
