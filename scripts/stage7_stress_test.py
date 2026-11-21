from stage7_integrity import *
optimized='--optimized' in sys.argv
assert json.loads((OUT/'stage7_1/recovery_gate.json').read_text())['status']=='PASS'
started=time.monotonic()
with Lab('stress',optimized) as lab:
 lab.start_agent();ready=lab.connected();lab.command(3,period=0);lab.command(1,count=5000)
 wait_for(lambda:lab.read()['received']==10000,240)
 final=lab.command(4);assert final['sampled']==final['published']==10000 and final['errors']==0,final
 lab.command(5);wait_for(lambda:'[REC] STOP' in (lab.d/'qemu.log').read_text(),5)
 p=lab.proof();p.update(compare(lab,10000));p.update(mcu_sampled=final['sampled'],mcu_published=final['published'],seconds=time.monotonic()-started,accelerated_period_ms=0,ticks_per_sec=1000)
record('stage7_2/optimized_stress' if optimized else 'stage7_2/stress',p);print('STRESS_PASS',optimized,p['seconds'])
