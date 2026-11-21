from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import os,pathlib,json,subprocess,signal,time,tempfile,random,pwd
def _terminate_owned_test(signum,frame):
    raise SystemExit(128+signum)
signal.signal(signal.SIGTERM,_terminate_owned_test)
ROOT=pathlib.Path(__file__).resolve().parents[1]
WS=work('ros2_stage5_ws')
OUT=pathlib.Path(os.environ.get('VEL_STAGE5_EVIDENCE',str(ROOT/'evidence/stage5'))); OUT.mkdir(parents=True,exist_ok=True)
def identity():
    nonroot()
    (WS/'runs').mkdir(parents=True,exist_ok=True)
    assert ROOT.stat().st_uid==os.getuid() and WS.stat().st_uid==os.getuid()
def rosenv(run_dir,domain=None):
    identity()
    env=ros_environment(); env.update(ROS_DOMAIN_ID=str(domain or random.SystemRandom().randrange(100,200)),ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',ROS_LOG_DIR=str(run_dir/'ros_logs'),RMW_IMPLEMENTATION='rmw_fastrtps_cpp',PYTHONUNBUFFERED='1')
    return env
class Processes:
    def __init__(self,directory,env): self.directory=directory; self.env=env; self.items=[]
    def start(self,name,cmd):
        f=(self.directory/(name+'.log')).open('w'); f.write('$ '+' '.join(map(str,cmd))+'\n'); f.flush()
        p=subprocess.Popen(list(map(str,cmd)),env=self.env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True); self.items.append((p,f)); return p
    def close(self):
        for p,f in reversed(self.items):
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
            f.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
def wait_for(predicate,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.1)
    raise TimeoutError('bounded checkpoint timed out')
def run_command(cmd,env,cwd=ROOT,timeout=30):
    return subprocess.run(list(map(str,cmd)),env=env,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
def record(name,data):
    f=OUT/(name+'.json');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(data,indent=2)+'\n')
