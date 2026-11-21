from stage7_runtime import *
optimized='--optimized' in sys.argv
assert json.loads((OUT/'stage7_1/recovery_gate.json').read_text())['status']=='PASS'
proof=[]
for fault in [False,True]:
 with Lab('gdb-fault' if fault else 'gdb-normal',optimized,paused=True) as lab:
  lab.start_agent();script=lab.d/'checks.gdb';elf=WS/('optimized_build' if optimized else 'baseline_build')/'zephyr/zephyr.elf'
  lines=['set pagination off','set confirm off','set breakpoint pending on',f'target remote 127.0.0.1:{lab.stub}','break main','continue','info registers','print/x $msp','print/x $psp','delete breakpoints','break uxr_create_session','continue','bt','delete breakpoints','break session_ready_marker','continue','print g_epoch','print g_state','delete breakpoints','break rclc_executor_spin_some','continue','bt','delete breakpoints','break rmw_publish','continue','bt','delete breakpoints']
  if fault:
   lines+=['break recovery_marker if g_state == 5',f'python import os,signal; os.kill({lab.agent.pid},signal.SIGTERM)','continue','print g_state','bt','delete breakpoints','break uxr_delete_session_retries','continue','bt',f'python open({str(lab.d/"restart-agent")!r},"w").close()','delete breakpoints','break uxr_create_session','continue','bt','delete breakpoints','break session_ready_marker','continue','print g_epoch','python assert int(gdb.parse_and_eval("g_epoch")) >= 2','delete breakpoints','break rclc_executor_spin_some','continue','bt','delete breakpoints','break rmw_publish','continue','bt','delete breakpoints']
  lines+=['printf "STAGE7_GDB_PATH_PASS\\n"','detach','quit'];script.write_text('\n'.join(lines)+'\n')
  errors=[]
  def restart():
   try:
    wait_for(lambda:(lab.d/'restart-agent').exists(),30);lab.agent.wait(4);lab.start_agent()
   except BaseException as e:errors.append(repr(e))
  thread=threading.Thread(target=restart) if fault else None
  if thread:thread.start()
  rc,log=run('gdb_fault' if fault else 'gdb_normal',['gdb-multiarch','-q','-nx','-batch',elf,'-x',script],lab.env,50)
  if thread:thread.join(5)
  assert not errors,errors;assert rc==0 and 'STAGE7_GDB_PATH_PASS' in log.read_text(),log.read_text()[-4000:]
  ready=lab.connected(epoch=1 if fault else 0);lab.command(3,period=0);lab.command(1,count=128);wait_for(lambda:lab.read()['received']==256,20);lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
  p=lab.proof();p.update(fault=fault,gdb_log=str(log),gdb_script=str(script),entity_recreation=fault,post_debug_records=256,session=ready['session_id']);proof.append(p)
record('stage7_2/optimized_gdb' if optimized else 'stage7_2/gdb',{'status':'PASS','paths':proof});print('GDB_PASS',optimized)
