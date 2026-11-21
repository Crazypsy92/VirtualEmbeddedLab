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
for i in range(2):
    stop('zephyr_thread_marker'); seen.append((v('_kernel.cpus[0].current'),v('$psp')))
    require(v('$control')&2,'thread PSP enabled'); require(0x20000000<=v('$psp')<0x20400000,'PSP valid AN385 RAM')
    gdb.execute('info registers'); gdb.execute('x/8wx $psp')
require(seen[0][0]!=seen[1][0] and seen[0][1]!=seen[1][1],'different Zephyr threads and stacks')
stop('zephyr_complete'); require(v('g_result')==0 and v('g_runs[0]')==8 and v('g_runs[1]')==8 and v('g_work')==1 and v('g_timer')>1,'kernel IPC runtime proof')
gdb.write('STAGE4_GDB_PASS\n')
end
detach
quit
