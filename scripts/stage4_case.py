#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import argparse,json,re
from stage4_support import *
from vel_jobs import install_cancel_handlers
install_cancel_handlers()
def stats(text): return dict((line[7:].split('=')[0],int(line.split('=')[1])) for line in text.splitlines() if line.startswith('[STAT] '))
def firmware(name,elf,expected=0):
    rc,text,_,expired=run(name,qemu(elf)); assert not expired and rc==expected and '[ERROR]' not in text and 'FATAL' not in text
    return stats(text)
def main(case):
    if case=='environment':
        rc,_=call('environment_setup',[sys.executable,ROOT/'scripts/setup_stage4.py'])
        assert rc==0
    elif case in ['hello','sync']:
        predicate=(lambda t:'Hello World!' in t) if case=='hello' else (lambda t:t.count('Hello World')>=4 and 'thread_a' in t and 'thread_b' in t)
        rc,text,reached,expired=run('stage4_1/'+case+'_official_run',[sys.executable,'-m','west','build','-d',ROOT/'build/zephyr'/case,'-t','run'],predicate,20,cwd=zephyr_base()); assert reached and not expired
    elif case=='kernel':
        z=firmware('stage4_1/kernel',ROOT/'build/zephyr/kernel/zephyr/zephyr.elf')
        assert z['worker_a']==8 and z['worker_b']==8 and z['preemption']==1 and z['priority']==1 and z['timer']>1 and z['work']==1 and z['uptime']>0 and z['result']==0
        assert min(z[x] for x in ['stack_a','stack_b','stack_main','stack_work'])>64
    elif case.endswith('_gdb'):
        rc,_=call(case,[os.sys.executable,ROOT/'scripts/gdb_stage4.py',case[:-4]],timeout=50); assert rc==0
    elif case=='sensor':
        z=firmware('stage4_2/sensor',ROOT/'build/zephyr/sensor/zephyr/zephyr.elf'); assert z['samples']==17 and z['concurrent']==80 and z['unavailable']==1 and z['result']==0
    elif case=='sensor_off':
        elf=ROOT/'build/zephyr/sensor_off/zephyr/zephyr.elf'; z=firmware('stage4_2/sensor_off',elf); assert z['driver_disabled']==1 and z['result']==0
        rc,text=call('stage4_2/sensor_off_symbols',['arm-none-eabi-nm',elf]); assert rc==0 and 'vel_api' not in text
    elif case=='missing_property':
        bad=ROOT/'build/zephyr/missing.overlay'; bad.write_text((ROOT/'zephyr/boards/sensors.overlay').read_text().replace('        step-millicelsius = <25>;',''))
        rc,text=build('stage4_2/sensor_missing',ROOT/'zephyr/apps/virtual_sensor_demo',['-DDTC_OVERLAY_FILE='+str(bad)]); assert rc!=0 and 'required' in text and 'step-millicelsius' in text
    elif case.startswith('acq'):
        i=int(case[3:]); z=firmware('stage4_3/case'+str(i),ROOT/f'build/zephyr/acquisition_cases/case{i}.elf',42 if i else 0)
        assert z['scenario']==i and z['mutex_timeouts']==1 and z['logged']==z['verified'] and z['hash']==z['read_hash']
        assert min(z['stack_'+str(n)] for n in range(4))>64 and z['stack_main']>64
        if i==0: assert z['produced_a']==128 and z['produced_b']==128 and z['received']==256 and z['logged']==256 and z['log_bytes']==5120 and z['result']==0 and 0<z['queue_peak']<=8
        else:
            expected={1:(-19,1),2:(-5,2),3:(-28,3),4:(-11,4),5:(-28,5),6:(-11,6)}
            assert (z['error'],z['location'])==expected[i] and z['result']==1 and z['stopped']==1
            if i==2: assert z['produced_a']==7
            if i==4: assert z['queue_peak']==8 and z['logged']==0
            if i==5: assert z['logged']==32 and z['received']==33
    elif case=='memory':
        rc,_=call('memory',[os.sys.executable,ROOT/'scripts/stage4_memory.py']); assert rc==0
    else: raise ValueError(case)
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('case'); a=ap.parse_args(); main(a.case); print('VERIFIED '+a.case)
