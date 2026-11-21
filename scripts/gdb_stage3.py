#!/usr/bin/env python3
import argparse,pathlib,socket,subprocess,time,sys,os
from run_qemu import ROOT,command,terminate
ap=argparse.ArgumentParser(); ap.add_argument('--elf',required=True); ap.add_argument('--mode',required=True); a=ap.parse_args()
out=pathlib.Path(os.environ.get('VEL_STAGE3_EVIDENCE',str(ROOT/'evidence/stage3')))/('stage3_1' if a.mode=='scheduler' else 'stage3_2' if a.mode=='fatfs' else 'stage3_3'); out.mkdir(parents=True,exist_ok=True)
with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
# Use guest instruction time so debugger breakpoints and host scheduling do not
# inject unexpected RTOS ticks while inspecting lock ownership.
cmd=command(pathlib.Path(a.elf))+['-icount','shift=3,align=off,sleep=off','-S','-gdb',f'tcp:127.0.0.1:{port}']
rc=1
with (out/(a.mode+'_gdb_qemu.log')).open('w') as log:
    log.write('$ '+' '.join(cmd)+'\n'); log.flush()
    proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError('stub exited')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1): break
            except OSError: time.sleep(.05)
        else: raise TimeoutError('stub startup')
        gcmd=['gdb-multiarch','-q','-nx','-batch',a.elf,'-ex',f'target remote 127.0.0.1:{port}','-x',str(ROOT/f'scripts/gdb_stage3_{a.mode}.gdb')]
        r=subprocess.run(gcmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=40)
        text='$ '+' '.join(gcmd)+'\n'+r.stdout+'\nGDB_EXIT='+str(r.returncode)+'\n'
        (out/(a.mode+'_gdb.log')).write_text(text); print(text)
        rc=0 if r.returncode==0 and 'STAGE3_GDB_PASS' in r.stdout else 1
    except (OSError,RuntimeError,TimeoutError,subprocess.TimeoutExpired) as e:
        (out/(a.mode+'_gdb.log')).write_text(str(e)); print(e)
    finally: terminate(proc); log.write('\nQEMU_REAPED='+str(proc.poll() is not None)+'\n')
sys.exit(rc)
