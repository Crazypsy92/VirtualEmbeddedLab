# Recovery design

DISCONNECTED -> WAITING_AGENT -> CONNECTING -> CONNECTED -> RUNNING. Failure enters RECOVERING, destroys initialized entities in reverse order and returns to WAITING_AGENT; STOPPED is terminal. Reconnect pauses acquisition until a new acknowledged START.

Discovery: 100 ms probes, maximum 12 failures, exponential backoff 100 to 800 ms. Active probes: 200 ms, three attempts. Maximum eight session creations and 900 seconds guest runtime, plus independent host deadlines. Allocator lifetime is static because RCLC retains its pointer. Cleanup uses official zero destroy timeout; UART IRQ/ring state is cleared after finalization.

Request IDs are monotonic within a boot. Last identical successful request returns 1 without side effects. Conflicting/older request returns 3; invalid parameters 2; unknown opcode 4; wrong boot/session 6. Opcodes: START 1, STOP 2, SET_RATE 3, STATUS 4, FINISH 5, software reboot 6. START count is the per-sensor total within a session; STOP retains sequence. Period 0 is accelerated simulation. Session changes reset sequence; physical sample indices persist until reboot. noinit boot identity survives software reset, not a power cycle.

ACK must match request ID. Timeout means uncertain execution, requiring status or an identical retry. Successful transport writes never substitute for ACK. Repeated cleanup must return live allocation to zero and preserve a stable connected allocation.
