from stage7_runtime import *
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--optimized',action='store_true');a=ap.parse_args();proof=[]
with Lab('recovery',a.optimized) as lab:
 time.sleep(1.5);lab.start_agent();first=lab.connected();boot=first['boot_id'];epochs=[]
 for cycle in range(3):
  ready=lab.read()['latest'];epoch=ready['session_id'];epochs.append(epoch)
  start=lab.command(1,count=100);same=lab.command(1,count=100,repeat=True,expect=1);assert same['start_effects']==start['start_effects']
  wait_for(lambda:lab.read()['received']>=10*(cycle+1),8)
  lab.stop_agent();wait_for(lambda:'state=5' in (lab.d/'qemu.log').read_text(),5);time.sleep(.4)
  lab.start_agent();new=lab.connected(epoch);assert new['boot_id']==boot and new['state']==3 and new['start_effects']==cycle+1
  lab.assert_same_mcu();assert lab.command(1,count=100,repeat=True,expect=1)['state']==3
 # Same MCU, new entities, finish 256 records in this session.
 ready=lab.read()['latest'];epoch=ready['session_id'];lab.command(3,period=0);lab.command(1,count=128)
 key=f"{boot}.{epoch}";wait_for(lambda:lab.read()['sessions'].get(key,{}).get('received')==[128,128],20)
 assert not lab.read()['errors'];lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 result=lab.proof();result.update(agent_restarts=3,same_qemu_throughout=True,epochs=epochs+[epoch],boot_id=boot,new_session_records=256)
 connected=[p['live'] for p in result['memory'] if p['live']>0];assert len(set(connected))==1,connected
 assert len(result['cleaned'])==4
proof.append(result)
with Lab('no-agent',a.optimized) as lab:
 wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),18);result=lab.proof();assert 'failures=12' in (lab.d/'qemu.log').read_text();result['finite_wait_stop']=True;proof.append(result)
record('stage7_1/optimized_recovery' if a.optimized else 'stage7_1/recovery_gate',{'status':'PASS','cases':proof});print('RECOVERY_GATE_PASS',a.optimized)
