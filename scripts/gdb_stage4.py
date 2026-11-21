#!/usr/bin/env python3
import argparse,socket,time,subprocess
from stage4_support import *
ap=argparse.ArgumentParser(); ap.add_argument('mode'); a=ap.parse_args()
name=a.mode; stage='stage4_1' if name=='kernel' else 'stage4_2' if name=='sensor' else 'stage4_3'
elf=ROOT/'build/zephyr'/name/'zephyr/zephyr.elf'
with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
path=OUT/stage/(name+'_gdb_qemu.log'); path.parent.mkdir(parents=True,exist_ok=True)
with path.open('w') as log:
    cmd=qemu(elf)+['-S','-gdb',f'tcp:127.0.0.1:{port}']; log.write('$ '+' '.join(cmd)+'\n'); log.flush()
    proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError('stub exited')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1): break
            except OSError: time.sleep(.05)
        else: raise TimeoutError('stub timeout')
        rc,text=call(stage+'/'+name+'_gdb',['gdb-multiarch','-q','-nx','-batch',elf,'-ex',f'target remote 127.0.0.1:{port}','-x',ROOT/f'scripts/gdb_stage4_{name}.gdb'],timeout=40)
        if rc or 'STAGE4_GDB_PASS' not in text: raise SystemExit(1)
    finally: stop(proc); log.write('\nreaped='+str(proc.poll() is not None)+'\n')
