from stage4_support import *
import json,re,shutil
source=ROOT/'zephyr/apps/data_acquisition'; cases=ROOT/'build/zephyr/acquisition_cases'; cases.mkdir(parents=True,exist_ok=True)
results={}
for i in range(7):
    overlays=[ROOT/'zephyr/boards/sensors.overlay']
    if i==2:
        overlays.append(ROOT/'zephyr/boards/acquisition_sensor_fault.overlay')
    rc,_=build('stage4_3/acquisition',source,['-DDTC_OVERLAY_FILE='+';'.join(map(str,overlays)),'-DSCENARIO='+str(i)])
    if rc: raise SystemExit(rc)
    for suffix in ['elf','bin','map']: shutil.copyfile(ROOT/f'build/zephyr/acquisition/zephyr/zephyr.{suffix}',cases/f'case{i}.{suffix}')
    rc,text,_,expired=run('stage4_3/case'+str(i),qemu(cases/f'case{i}.elf'))
    z=dict((line[7:].split('=')[0],int(line.split('=')[1])) for line in text.splitlines() if line.startswith('[STAT] ')); results[str(i)]=z
    assert not expired and rc==(42 if i else 0) and '[ERROR]' not in text and z['scenario']==i and z['mutex_timeouts']==1
    assert z['logged']==z['verified'] and z['hash']==z['read_hash'] and min(z[f'stack_{n}'] for n in range(4))>64
    if i==0: assert z['produced_a']==128 and z['produced_b']==128 and z['received']==256 and z['logged']==256 and z['log_bytes']==5120 and z['result']==0
    else:
        expected={1:(-19,1),2:(-5,2),3:(-28,3),4:(-11,4),5:(-28,5),6:(-11,6)}
        assert (z['error'],z['location'])==expected[i] and z['result']==1 and z['stopped']==1
        if i==2: assert z['produced_a']==7
        if i==5: assert z['logged']==32 and z['received']==33
    print('CASE',i,'VERIFIED',flush=True)
# Restore normal compiled app; fault ELFs remain separate.
rc,_=build('stage4_3/acquisition',source,['-DDTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/sensors.overlay'),'-DSCENARIO=0'])
assert rc==0
(OUT/'stage4_3/cases.json').write_text(json.dumps(results,indent=2)+'\n')
