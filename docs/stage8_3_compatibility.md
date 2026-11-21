# Stage 8.3 compatibility gate

Fixed local Zephyr 4.4.2: dccb09599635bdff17633fa7e9dab014b91dce90. Audited samples/subsys/modbus/{tcp_server,tcp_gateway,rtu_client,rtu_server}, subsys/modbus/{modbus_raw,modbus_core,modbus_serial}.c and include/zephyr/modbus/modbus.h. Prior Stage8.2 report and clean ff7e1ad baseline were checked first.

| Check | Result and scope |
|---|---|
| Official TCP Server sample | PASS source/API audit; unmodified sample runtime not claimed |
| Official TCP Gateway sample | PASS source/API audit; independent adapted application built and exercised |
| RTU Client API | PASS real backend transaction over dual PTY |
| TCP public helpers | PASS get_header/put_header/backend_txn used in compiled gateway |
| native_sim TCP socket | PASS actual loopback echo followed by Modbus forwarding |
| Offloaded Sockets | PASS using local official overlay-nsos.conf settings |
| TCP plus PTY | PASS two native processes, real bytes and independent pymodbus client |

Official gateway sample handles one accepted client at a time and uses blocking MSG_WAITALL without this task's complete bounded stream validation and queue lifecycle. The new independent app retains its public ADU conversion/backend API sequence and adds stream framing, validation and multi-client scheduling. It is not an unchanged official sample qualification. Original third-party sources are untouched.

Native configuration follows samples/net/sockets/echo_server/overlay-nsos.conf: NET_DRIVERS, NET_SOCKETS_OFFLOAD, NET_NATIVE_OFFLOADED_SOCKETS; ETH_NATIVE_TAP=n. No TAP, root or WSL global change. Default ZVFS_POLL_MAX=3 was insufficient for listener plus four clients and produced ENOMEM in the initial test; qualified config is 8 and bounded heap 32768. Official native PTY lacks runtime UART configure, so requested 115200 8E1 remains software configuration with UART_USE_RUNTIME_CONFIGURE=n. No physical serial parameters are measured.

modbus_raw_backend_txn preserves transaction/protocol identifiers on serial return and supplies exception 11 on backend errors. The application additionally enforces Unit1 route (exception10), verifies returned unit/function, and refuses malformed protocol/length headers before the public helper clamps length. Official RTU CRC generation/checking and UART receive/transmit remain unchanged. API timeout 500000 us, no retransmit loop in modbus_tx_wait_rx_adu. Hardware Ethernet and RS485 are NOT TESTED.
