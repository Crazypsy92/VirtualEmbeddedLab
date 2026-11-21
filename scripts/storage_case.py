#!/usr/bin/env python3
"""Only orchestrates C tests; all storage/filesystem implementation stays in C."""
import argparse,pathlib,subprocess,tempfile,sys,selectors,os,signal,hashlib
ap=argparse.ArgumentParser()
ap.add_argument('--exe',required=True)
ap.add_argument('--case',required=True)
ap.add_argument('--root',required=True)
a=ap.parse_args()
root=pathlib.Path(a.root).absolute()
root.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix=a.case+'-',dir=root) as temp:
    modes={'persistence':['persist-write','persist-read'], 'cross-process':['cross-write','cross-read','cross-verify'], 'stress':['stress-write','stress-read'], 'crash':['crash-seed','crash-write','crash-observe']}.get(a.case,[a.case])
    outside=None
    env=os.environ.copy()
    if a.case=='safety':
        outside=root/(pathlib.Path(temp).name+'.sentinel')
        outside.write_bytes(b'OUTSIDE TEST DIRECTORY: MUST NOT CHANGE')
        expected_hash=hashlib.sha256(outside.read_bytes()).hexdigest()
        env['VEL_SAFETY_OUTSIDE']=str(outside)
    for mode in modes:
        cmd=[a.exe,mode,temp]
        print('$ '+' '.join(cmd),flush=True)
        if mode=='crash-write':
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
            try:
                with selectors.DefaultSelector() as sel:
                    sel.register(child.stdout,selectors.EVENT_READ)
                    if not sel.select(5): raise TimeoutError('crash child never reached unsynced checkpoint')
                # Read using communicate after kill: readiness line is flushed, and pipe is bounded here.
                line=child.stdout.readline()
                print(line,end='',flush=True)
                if 'CRASH_READY' not in line: raise RuntimeError('unexpected crash checkpoint output')
                os.killpg(child.pid,signal.SIGKILL)
                tail,_=child.communicate(timeout=3)
                print(tail,end='')
                if child.returncode != -signal.SIGKILL: raise RuntimeError('abnormal termination not observed')
                print('ACTUAL_SIGKILL pid='+str(child.pid)+' exit='+str(child.returncode),flush=True)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGKILL); child.wait(timeout=3)
        else:
            r=subprocess.run(cmd,timeout=15,env=env)
            if r.returncode: sys.exit(r.returncode)

    if outside is not None:
        if hashlib.sha256(outside.read_bytes()).hexdigest()!=expected_hash: raise RuntimeError('outside sentinel modified')
        print('OUTSIDE_SENTINEL_SHA256='+expected_hash+' unchanged=yes')
        outside.unlink()
