from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import os,pathlib,json,subprocess,time,signal,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1];WS=work('simulation_stage8_1_ws');OUT=pathlib.Path(os.environ.get('VEL_STAGE8_1_EVIDENCE',str(ROOT/'evidence/stage8_1')));Z=zephyr_base().parent
def record(n,v):
 p=OUT/(n+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def run(n,cmd,timeout=300,env=None,cwd=ROOT):
 (WS/'runs').mkdir(parents=True,exist_ok=True)
 path=WS/'runs'/(n+'-'+str(time.monotonic_ns())+'.log');started=time.monotonic()
 with path.open('w') as f:
  f.write('$ '+' '.join(map(str,cmd))+'\n');f.flush();p=subprocess.Popen(list(map(str,cmd)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout)
  except BaseException as e:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(3)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(3)
   if not isinstance(e,subprocess.TimeoutExpired):raise
   rc=124
 result={'exit':rc,'log':str(path),'seconds':time.monotonic()-started,'command':list(map(str,cmd))};print(n,result,flush=True);return result

def gate():
 if os.environ.get('VEL_STAGE8_1_LOCAL_ONLY')=='1':return
 a=json.loads((WS/'regression/stage7/acceptance.json').read_text());assert a['status'].startswith('Stage 7 SOFTWARE PASS') and sum(c['tests'] for c in a['ctest_counts'].values())==133
