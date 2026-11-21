from stage7_integrity import *
optimized='--optimized' in sys.argv
assert json.loads((OUT/'stage7_1/recovery_gate.json').read_text())['status']=='PASS'
cases=[]
with Lab('uart-cut',optimized) as lab:
 lab.start_agent();ready=lab.connected();lab.command(1,count=5000);wait_for(lambda:lab.read()['received']>=10,8)
 old=ready['session_id'];lab.relay.cut=True
 wait_for(lambda:'state=5' in (lab.d/'qemu.log').read_text(),8);time.sleep(.4);lab.relay.cut=False
 new=lab.connected(old);assert new['state']==3 and new['boot_id']==ready['boot_id'];lab.assert_same_mcu()
 lab.command(3,period=0);lab.command(1,count=128);key=f"{new['boot_id']}.{new['session_id']}"
 wait_for(lambda:lab.read()['sessions'].get(key,{}).get('received')==[128,128],20)
 lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 p=lab.proof();assert lab.relay.dropped>0;p.update(scenario='uart_cut_restore',same_qemu=True,same_agent=True,new_session=new['session_id']);cases.append(p)
with Lab('subscriber-controls',optimized) as lab:
 lab.start_agent();lab.connected();initial=lab.command(3,period=5)
 duplicate=lab.command(3,period=5,repeat=True,expect=1);assert duplicate['rate_effects']==initial['rate_effects']
 invalid=lab.command(3,period=201,expect=2);assert invalid['period_ms']==5 and invalid['rate_effects']==initial['rate_effects']
 invalidstart=lab.command(1,count=5001,expect=2);assert invalidstart['start_effects']==0
 lab.command(1,count=128);wait_for(lambda:lab.read()['received']>=10,8)
 os.killpg(lab.peer.pid,signal.SIGSTOP);before=lab.read()['received'];time.sleep(.6);assert lab.read()['received']==before
 os.killpg(lab.peer.pid,signal.SIGCONT);wait_for(lambda:lab.read()['received']==256,20)
 stop=lab.command(2);assert stop['state']==3;time.sleep(.3);assert lab.read()['received']==256
 # A real stopped MCU cannot acknowledge a new command; host must time out.
 os.killpg(lab.qemu.pid,signal.SIGSTOP);timedout=False;t=time.monotonic()
 try:lab.command(4,timeout=.5)
 except TimeoutError:timedout=True
 finally:os.killpg(lab.qemu.pid,signal.SIGCONT)
 assert timedout and time.monotonic()-t<3
 wait_for(lambda:any(a['request_id']==lab.request for a in lab.read()['acks']),8)
 lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 p=lab.proof();p.update(compare(lab,256));p.update(scenario='subscriber_pause_duplicate_invalid_stop_ack_timeout',timeout_observed=timedout,timeout_seconds=time.monotonic()-t,paused_seconds=.6);cases.append(p)
with Lab('software-reboot',optimized) as lab:
 lab.start_agent();old=lab.connected();lab.command(1,count=128);wait_for(lambda:lab.read()['received']==256,15)
 lab.command(6);wait_for(lambda:lab.read()['latest'].get('boot_id',0)>old['boot_id'],20);new=lab.connected(boot=old['boot_id']+1)
 lab.assert_same_mcu();assert new['state']==3
 # Delayed command addressed to previous boot must not execute on new boot.
 nack=lab.command(1,target=old,expect=6);assert nack['start_effects']==0
 lab.command(3,period=0);lab.command(1,count=128);wait_for(lambda:lab.read()['received']==512,20)
 lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 p=lab.proof();p.update(compare(lab,512));assert p['boot_count']==2;p.update(scenario='software_reboot',old_boot=old['boot_id'],new_boot=new['boot_id']);cases.append(p)
# Interrupt real entity creation after publishers exist but before subscription init.
with Lab('partial-create',optimized,paused=True) as lab:
 lab.start_agent();elf=WS/('optimized_build' if optimized else 'baseline_build')/'zephyr/zephyr.elf';script=lab.d/'partial.gdb'
 lines=['set pagination off','set confirm off',f'target remote 127.0.0.1:{lab.stub}','break rclc_subscription_init_default','continue','bt',f'python import os,signal;os.kill({lab.agent.pid},signal.SIGTERM)','delete breakpoints','detach','quit'];script.write_text('\n'.join(lines)+'\n')
 rc,log=run('partial_create_gdb',['gdb-multiarch','-q','-nx','-batch',elf,'-x',script],lab.env,25);assert rc==0
 lab.agent.wait(4);wait_for(lambda:'phase=cleaned' in (lab.d/'qemu.log').read_text(),15)
 lab.start_agent();new=lab.connected(epoch=1);lab.assert_same_mcu();lab.command(3,period=0);lab.command(1,count=128);wait_for(lambda:lab.read()['received']==256,20)
 lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 p=lab.proof();p.update(compare(lab,256));p.update(scenario='partial_entity_create_cleanup',gdb_log=str(log),new_session=new['session_id']);assert len(p['cleaned'])>=2;cases.append(p)
record('stage7_2/optimized_faults' if optimized else 'stage7_2/faults',{'status':'PASS','cases':cases});print('FAULT_MATRIX_PASS',optimized)
