from vel_env import tool, zephyr_environment, zephyr_base
from pathlib import Path
import sys
"""Pinned external Zephyr environment; all processes bounded and owned."""
import os,pathlib,subprocess,signal,time,selectors
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=zephyr_base().parent
OUT=pathlib.Path(os.environ.get('VEL_STAGE4_EVIDENCE',str(ROOT/'evidence/stage4')))
def environment():
    return zephyr_environment("cross-compile")
def call(name,cmd,cwd=ROOT,timeout=180):
    path=OUT/(name+'.log'); path.parent.mkdir(parents=True,exist_ok=True)
    try:
        r=subprocess.run(list(map(str,cmd)),cwd=cwd,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        rc=r.returncode; text=r.stdout
    except (OSError,subprocess.TimeoutExpired) as e: rc=1; text=str(e)
    path.write_text('$ '+' '.join(map(str,cmd))+'\n'+text+'\nexit='+str(rc)+'\n'); print(name,rc,flush=True)
    if rc: print(text[-6000:])
    return rc,text
def build(name,source,extra=()):
    return call(name+'_build',[sys.executable,'-m','west','build','-b','mps2/an385',source,'-d',ROOT/'build/zephyr'/name.split('/')[-1],'--','-DDTC='+str(Path(tool('dtc'))),'-DCONFIG_BUILD_OUTPUT_BIN=y',*extra],cwd=zephyr_base())
def stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid,signal.SIGTERM)
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait(timeout=3)
def run(name,cmd,until=None,timeout=15,cwd=ROOT):
    path=OUT/(name+'.log'); path.parent.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(list(map(str,cmd)),cwd=cwd,env=environment(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    output=b''; reached=False; expired=False
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout,selectors.EVENT_READ); deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                for key,_ in sel.select(.1):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if chunk: output+=chunk
                if until and until(output.decode(errors='replace')): reached=True; break
                if proc.poll() is not None: output+=proc.stdout.read(); break
            else: expired=True
        if reached: stop(proc)
        if expired: stop(proc)
    finally: stop(proc)
    text=output.decode(errors='replace'); path.write_text('$ '+' '.join(map(str,cmd))+'\n'+text+'\nexit='+str(proc.returncode)+'\ncheckpoint='+str(reached)+'\ntimeout='+str(expired)+'\nreaped='+str(proc.poll() is not None)+'\n')
    print(name,'exit',proc.returncode,'checkpoint',reached,'timeout',expired,flush=True)
    return proc.returncode,text,reached,expired
def qemu(elf): return ['qemu-system-arm','-M','mps2-an385','-cpu','cortex-m3','-display','none','-monitor','none','-serial','stdio','-semihosting-config','enable=on,target=native','-kernel',str(elf)]
