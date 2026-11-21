#!/usr/bin/env python3
import argparse,pathlib,subprocess,sys,re,json,os
from run_qemu import ROOT,command,terminate
from vel_jobs import install_cancel_handlers
install_cancel_handlers()
ap=argparse.ArgumentParser(); ap.add_argument('--elf',required=True); ap.add_argument('--mode',required=True); a=ap.parse_args()
out=pathlib.Path(os.environ.get('VEL_STAGE3_EVIDENCE',str(ROOT/'evidence/stage3')))/('stage3_1' if a.mode=='scheduler' else 'stage3_2' if a.mode=='fatfs' else 'stage3_3'); out.mkdir(parents=True,exist_ok=True)
cmd=command(pathlib.Path(a.elf)); proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
rc=1; text=''
try:
    try:
        text,_=proc.communicate(timeout=12)
        stats={k:int(v) for k,v in re.findall(r'\[STAT\] (\w+)=(\d+)',text)}
        expected_error=a.mode.startswith('logger') and int(a.mode[6:])!=0
        if proc.returncode!=(42 if expected_error else 0) or '[ERROR]' in text: raise ValueError('QEMU firmware failed')
        if stats.get('result')!=(1 if expected_error else 0) or stats.get('ticks',0)<5 or stats.get('switches',0)<2: raise ValueError('missing runtime proof')
        if a.mode=='scheduler':
            if not (stats.get('priority')==1 and stats.get('preemption')==1 and stats.get('context_ok')==2 and stats.get('worker_a',0)>0 and stats.get('worker_b',0)>0 and stats.get('switches',0)>20 and stats.get('malloc_expected')==1 and min(stats.get(k,0) for k in ['stack_a','stack_b','stack_monitor','stack_high','stack_idle'])>32): raise ValueError('scheduler evidence invalid')
        if a.mode=='fatfs':
            h=2166136261
            for i in range(8193): h=((h^(((i*31+(i>>3))^0x5A)&255))*16777619)&0xffffffff
            if not (stats.get('fs_bytes')==8193 and stats.get('fs_hash')==h and stats.get('remount')==1 and stats.get('ram_faults')==2 and stats.get('space_restored')==1 and stats.get('ram_bytes')==2097152 and stats.get('fat_type')==1 and stats.get('stack_fs',0)>32 and stats.get('stack_idle',0)>32): raise ValueError('ARM FatFs evidence invalid')
        if a.mode.startswith('logger'):
            case=int(a.mode[6:])
            if any(stats.get(k,1)!=0 for k in ['asserts','hardfaults','stack_faults']): raise ValueError('unexpected runtime hook')
            if stats.get('scenario')!=case or stats.get('fs_takes')!=stats.get('fs_gives') or stats.get('fs_timeouts')!=1 or stats.get('queue_timeout')!=1 or min(stats.get(k,0) for k in ['stack_logger','stack_reader','stack_monitor','stack_sensor_a','stack_sensor_b','stack_idle'])<=32: raise ValueError('synchronization/resources invalid')
            if case==0 and not (stats.get('produced_a')==128 and stats.get('produced_b')==128 and stats.get('written')==256 and stats.get('verified')==256 and stats.get('file_bytes')==5120 and stats.get('model_hash')==stats.get('read_hash') and stats.get('reader_ops',0)>0 and stats.get('fs_contention',0)>1 and stats.get('stopped')==0): raise ValueError('logging model invalid')
            if case in [1,2,3] and not (stats.get('error_code')==1 and stats.get('fault_hits')==1): raise ValueError('storage error missing')
            if case==1 and stats.get('written',256)>=256: raise ValueError('write failure claimed complete')
            if case==2 and not (stats.get('partial_blocks')==1 and stats.get('written')==0 and stats.get('fault_blocks')==1 and stats.get('fault_bytes')==512): raise ValueError('partial write evidence')
            if case==3 and not (stats.get('written')==256 and stats.get('verified')==0): raise ValueError('read failure evidence')
            if case==4 and not (stats.get('malloc_expected')==1 and stats.get('error_code')==100): raise ValueError('malloc hook evidence')
            if case==5 and stats.get('error_code')!=15: raise ValueError('mutex timeout missing')
            if case==6 and stats.get('error_code')!=101: raise ValueError('queue full missing')
            if case and stats.get('stopped')!=1: raise ValueError('error not stopped')
        rc=0
    except (subprocess.TimeoutExpired,ValueError) as e: text+='\nVALIDATION_ERROR '+str(e)+'\n'
finally:
    terminate(proc)
    text='$ '+' '.join(cmd)+'\nQEMU_PID='+str(proc.pid)+'\n'+text+'\nQEMU_EXIT='+str(proc.returncode)+'\nRUNNER_EXIT='+str(rc)+'\n'
    (out/(a.mode+'.log')).write_text(text); print(text)
sys.exit(rc)
