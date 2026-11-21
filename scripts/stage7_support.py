from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage6_support import identity,rosenv
import os,pathlib,json,subprocess,signal,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1];WS=work('micro_ros_stage7_ws');OLD=work('micro_ros_stage6_ws');OUT=pathlib.Path(os.environ.get('VEL_STAGE7_EVIDENCE',str(ROOT/'evidence/stage7')))
def record(name,data):
 p=OUT/(name+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')
def run(name,cmd,env=None,timeout=600,cwd=ROOT):
 identity();(WS/'runs').mkdir(parents=True,exist_ok=True);p=WS/'runs'/(name+'-'+str(time.monotonic_ns())+'.log')
 with p.open('w') as f:
  f.write('$ '+' '.join(map(str,cmd))+'\n');f.flush();proc=subprocess.Popen(list(map(str,cmd)),cwd=cwd,env=env or tool_environment(),stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=proc.wait(timeout)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(4)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(4)
   rc=124
  except BaseException:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(4)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(4)
   raise
 print(name,rc,p,flush=True)
 if rc:print(p.read_text()[-4000:])
 return rc,p
