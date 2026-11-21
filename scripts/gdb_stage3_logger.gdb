set pagination off
set confirm off
set remotetimeout 5
python
import gdb
def val(e): return int(gdb.parse_and_eval('(unsigned long)('+e+')'))
def check(ok,msg):
    if not ok: raise gdb.GdbError('ASSERT FAIL: '+msg)
    gdb.write('ASSERT PASS: '+msg+'\n')
def stop(name,condition=None):
    a=val('&'+name)&~1; bp=gdb.Breakpoint('*'+hex(a),temporary=True)
    if condition: bp.condition=condition
    gdb.execute('continue'); check(val('$pc')==a,'breakpoint '+name)
stop('vTaskStartScheduler')
stop('logger_write_marker'); check(val('pxCurrentTCB')==val('g_logger_handle'),'Logger task owns CPU')
check(val('$control')&2 and val('$psp')!=val('$msp'),'Logger PSP distinct from MSP')
stop('f_write','pxCurrentTCB == g_logger_handle'); check(val('pxCurrentTCB')==val('g_logger_handle'),'Logger calls actual FatFs f_write')
stop('fs_lock_marker','pxCurrentTCB == g_logger_handle')
check(val('g_fs_owner')==val('g_logger_handle'),'recorded filesystem lock owner')
check(val('((Queue_t*)g_fs_mutex[0])->u.xSemaphore.xMutexHolder')==val('g_logger_handle'),'actual FreeRTOS Mutex holder is Logger')
gdb.execute('info registers')
stop('fs_unlock_marker','pxCurrentTCB == g_logger_handle')
check(val('((Queue_t*)g_fs_mutex[0])->u.xSemaphore.xMutexHolder')==val('g_logger_handle'),'Mutex still owned before give')
stop('vel_complete')
check(val('g_written')==256 and val('g_verified')==256 and val('g_file_bytes')==5120,'256 real records written and reread')
check(val('g_model_hash')==val('g_read_hash'),'production/readback hashes match')
check(val('g_fs_takes')==val('g_fs_gives') and val('g_fs_owner')==0,'locks released and balanced')
check(val('g_fs_contention')>1 and val('g_reader_ops')>0 and val('g_fs_timeouts')==1,'real same-volume contention and finite timeout')
check(val('g_result')==0 and val('g_error_code')==0 and val('g_hardfaults')==0 and val('g_stack_faults')==0 and val('g_asserts')==0,'clean logger completion')
gdb.write('STAGE3_GDB_PASS\n')
end
detach
quit
