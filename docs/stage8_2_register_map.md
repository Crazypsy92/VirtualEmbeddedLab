# Device register map

Addresses are zero-based protocol offsets. Registers use big-endian 16-bit data; RTU CRC is low-byte first. Coil bit zero is the lowest addressed output. Slave address 1, software 115200 8E1. All counters exposed as registers wrap modulo 65536; diagnostic logs preserve 32-bit totals.

| Space | Addresses | Permission / meaning |
|---|---|---|
| Coils | 0..7 | R/W GPIO outputs 0..7; FC01/05/0F |
| Discrete inputs | 0..3 | Read GPIO8..11 through FC02; separate test-control PTY changes external input levels |
| Holding 0 | 0 | Mode R/W 0..2; 0 pauses sampling, nonzero enables periodic sampling; mode reported in status |
| Holding 1 | 1 | Sample period R/W 1..1000 milliseconds |
| Holding 2 | 2 | Alarm threshold R/W 0..1000 samples since boot; status bit8 indicates exceeded threshold |
| Holding 3 | 3 | Output mask R/W 0..255; applied through GPIO API; coil writes update it |
| Holding 4 | 4 | Heartbeat interval R/W 1..1000 milliseconds; actual heartbeat counter in logs |
| Holding 5 | 5 | Read-only successful addressed write-command count; one increment per accepted write frame |
| Holding 6..7 | 6..7 | Reserved, read zero, write rejected |
| Input 0 | 0 | Mode bits plus alarm bit8 |
| Input 1..2 | 1..2 | Uptime ms low16/high16; separate requests are not an atomic snapshot |
| Input 3 | 3 | Received frame work-handler count, including malformed frames |
| Input 4 | 4 | Responses prepared; not physical TX-confirmed delivery |
| Input 5 | 5 | CRC/frame/application exception errors |
| Input 6 | 6 | Actual DI bitmap |
| Input 7 | 7 | Actual DO bitmap |

Holding/Input arrays are 8 words. FC03 and FC04 read them; FC06/10 write only holding0..4. Input registers have no write function code. Invalid read addresses return exception2; invalid quantity/value exception3; unsupported function exception1. All multi-write ranges/values are prevalidated, so rejected requests do not change any output/configuration. Successful repeated absolute writes set the same value (RTU has no request ID or exactly-once semantics); command counter records accepted requests, not value changes. No retry is hidden in the independent master (retries=0).

GPIO0..7 are accessed through standard GPIO APIs. Test-control UART0 accepts A..P to inject DI bitmaps 0..15 using the official GPIO emulator input interface, S to request diagnostics, and R to query RX readiness on the native_sim adapter. This control channel is not Modbus and cannot write device holding registers. UART1 is exclusively the official Modbus RTU server. DE16 and RE17 are logical software direction signals. Main-loop diagnostics include rising/falling callback counts, samples, heartbeats, direction transitions and stack watermarks. GPIO emulator output API returns the whole port in this pinned version, so bitmaps are explicitly masked.
