#!/usr/bin/env python3
"""Start a private GDB stub, bound all waits, clean up QEMU in finally."""
import pathlib
import os
import socket
import subprocess
import sys
import time
from run_qemu import ROOT, command, terminate
out = pathlib.Path(os.environ.get('VEL_STAGE1_EVIDENCE', str(ROOT/'evidence/stage1')))
out.mkdir(parents=True, exist_ok=True)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
cmd = command(ROOT/'build/arm/cortex_m3_demo.elf') + ['-S', '-gdb', f'tcp:127.0.0.1:{port}']
rc = 1
with (out/'gdb_qemu.log').open('w') as qlog:
    qlog.write('$ ' + ' '.join(cmd) + '\n'); qlog.flush()
    proc = subprocess.Popen(cmd, stdout=qlog, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if proc.poll() is not None: raise RuntimeError('QEMU stub exited early')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=0.1): break
            except OSError: time.sleep(0.05)
        else: raise TimeoutError('GDB stub startup timeout')
        gcmd = ['gdb-multiarch', '-q', '-nx', '-batch', str(ROOT/'build/arm/cortex_m3_demo.elf'), '-ex', f'target remote 127.0.0.1:{port}', '-x', str(ROOT/'scripts/gdb_verify.gdb')]
        r = subprocess.run(gcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        (out/'gdb.log').write_text('$ ' + ' '.join(gcmd) + '\n' + r.stdout + '\nGDB_EXIT=' + str(r.returncode) + '\n')
        print(r.stdout)
        rc = 0 if r.returncode == 0 and 'GDB_VALIDATION_PASS' in r.stdout else 1
    except (OSError, RuntimeError, subprocess.TimeoutExpired, TimeoutError) as e:
        (out/'gdb.log').write_text('FAILED: ' + str(e) + '\n')
        print(e)
    finally:
        terminate(proc)
        qlog.write('\nQEMU_REAPED=' + str(proc.poll() is not None) + '\n')
sys.exit(rc)
