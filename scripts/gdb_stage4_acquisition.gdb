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
seen=[]
for i in range(3):
    stop('acquisition_thread_marker'); seen.append((v('_kernel.cpus[0].current'),v('$psp')))
require(len(set(x[0] for x in seen))==3 and len(set(x[1] for x in seen))==3,'distinct acquisition threads/PSP')
stop('fetch'); require(v('$r0')!=0,'production uses real Sensor API device dispatch')
stop('acquisition_lock_marker'); require(v('log_lock.owner')==v('_kernel.cpus[0].current'),'logger owns real Zephyr mutex'); gdb.execute('info registers')
stop('acquisition_complete')
require(v('g_result')==0 and v('g_produced[0]')==128 and v('g_produced[1]')==128 and v('g_received')==256 and v('g_logged')==256 and v('g_verified')==256,'256 production/readback records')
require(v('g_hash')==v('g_read_hash') and v('g_error')==0 and v('log_lock.owner')==0,'matching hashes and released lock')
for i in range(256):
    base='ram_log[%d].'%i
    sensor=v(base+'sensor'); seq=v(base+'sequence'); value=v(base+'value')
    require(sensor<2 and seq<128 and value==(30000 if sensor else 25000)+seq*(40 if sensor else 25),'record %d deterministic value'%i)
gdb.write('GDB_ALL_256_RECORDS_INSPECTED\n')
gdb.write('STAGE4_GDB_PASS\n')
end
detach
quit
