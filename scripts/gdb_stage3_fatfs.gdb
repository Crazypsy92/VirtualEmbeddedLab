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
    a=val('&'+name)&~1; gdb.Breakpoint('*'+hex(a),temporary=True); gdb.execute('continue'); check(val('$pc')==a,'breakpoint '+name)
stop('f_mkfs'); check(val('$control')&2,'mkfs runs in ARM task PSP')
stop('f_write'); check(0x20200000<=val('$psp')<0x203fc000,'ARM FatFs task stack')
stop('disk_write'); gdb.execute('info registers')
stop('vel_complete')
check(val('g_fs_bytes')==8193 and val('g_fs_remount')==1 and val('g_ram_faults')==2,'actual ARM file verification and RAM faults')
check(val('&ram_bytes')==0x20000000 and val('&_ramdisk_end')==0x20200000,'2 MiB RAM disk isolated from heap/stacks')
check(val('&_ebss')<val('&_stack_limit'),'static RAM below MSP reserve')
check(val('g_result')==0 and val('g_hardfaults')==0 and val('g_asserts')==0,'clean ARM filesystem completion')
gdb.write('STAGE3_GDB_PASS\n')
end
detach
quit
