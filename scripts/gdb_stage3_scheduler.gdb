set pagination off
set confirm off
set remotetimeout 5
python
import gdb
def val(e): return int(gdb.parse_and_eval('(unsigned long)('+e+')'))
def check(ok,msg):
    if not ok: raise gdb.GdbError('ASSERT FAIL: '+msg)
    gdb.write('ASSERT PASS: '+msg+'\n')
def stop(name):
    address=val('&'+name)&~1
    gdb.Breakpoint('*'+hex(address),temporary=True)
    gdb.execute('continue')
    check(val('$pc')==address,'breakpoint '+name)
stop('vTaskStartScheduler')
stop('SVC_Handler'); check(val('$xpsr')&511==11,'official SVC starts scheduler')
stop('PendSV_Handler'); check(val('$xpsr')&511==14,'official PendSV active')
gdb.execute('stepi'); check(val('$r0')==val('$psp'),'PendSV captures outgoing PSP')
gdb.execute('x/8wx $r0'); gdb.execute('disassemble PendSV_Handler')
stop('SysTick_Handler'); before=val('g_tick_hook'); check(val('$xpsr')&511==15,'SysTick exception')
stop('SysTick_Handler'); check(val('g_tick_hook')>before,'successive SysTick interrupts')
seen=[]
for i in range(2):
    stop('task_marker'); check(val('$control')&2,'thread uses PSP')
    current=val('pxCurrentTCB'); psp=val('$psp'); msp=val('$msp')
    check(0x20200000<=psp<0x203fc000 and 0x203fc000<=msp<=0x20400000,'PSP heap stack / MSP reserved stack')
    seen.append((current,psp)); gdb.execute('info registers'); gdb.execute('x/12wx $psp')
check(seen[0][0]!=seen[1][0] and seen[0][1]!=seen[1][1],'two distinct TCBs and PSP stacks')
stop('vel_complete')
check(val('g_context_ok')==2,'R4/R5 canaries and SP survived blocking switches')
check(val('g_workers[0]')>0 and val('g_workers[1]')>0 and val('g_switches')>20,'both equal-priority CPU loops scheduled')
check(val('g_result')==0 and val('g_asserts')==0 and val('g_stack_faults')==0 and val('g_hardfaults')==0,'clean runtime completion')
gdb.write('STAGE3_GDB_PASS\n')
end
detach
quit
