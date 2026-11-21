set pagination off
set confirm off
set remotetimeout 5
python
import gdb
def v(e): return int(gdb.parse_and_eval('(unsigned long)('+e+')'))
def require(ok,msg):
    if not ok: raise gdb.GdbError(msg)
    gdb.write('ASSERT PASS '+msg+'\n')
def stop(n):
    bp=gdb.Breakpoint('*'+hex(v('&'+n)&~1),temporary=True); gdb.execute('continue')
stop('main')
stop('fetch'); require(v('$r0')!=0,'Device Model dispatches real device to sensor fetch'); gdb.execute('info registers')
stop('sensor_complete'); require(v('g_result')==0 and v('g_sensor_samples')==17 and v('g_concurrent_samples')==80,'standard Sensor API and concurrent counts verified')
gdb.write('STAGE4_GDB_PASS\n')
end
detach
quit
