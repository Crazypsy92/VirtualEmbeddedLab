from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import os,pathlib,pwd,json,subprocess,signal,tempfile,time
def _terminated(signum,frame):raise SystemExit(128+signum)
signal.signal(signal.SIGTERM,_terminated)
ROOT=pathlib.Path(__file__).resolve().parents[1];WS=work('micro_ros_stage6_ws');OUT=pathlib.Path(os.environ.get('VEL_STAGE6_EVIDENCE',str(ROOT/'evidence/stage6')))
def identity():
 nonroot()
 (WS/'runs').mkdir(parents=True,exist_ok=True)
 assert ROOT.stat().st_uid==WS.stat().st_uid==os.getuid()
def micro_ros_blockers(stage):
 issues=[]
 try:
  distro=ros_environment().get('ROS_DISTRO')
 except (SystemExit, subprocess.SubprocessError):
  distro=None
 if distro!='lyrical':
  issues.append(f"Stage {stage} dependency set requires ROS 2 Lyrical. Active ROS: {distro or 'none'}")
 required=['micro_ros/dependencies.lock.json','micro_ros/arm/colcon.meta']
 if stage==7:required.append('micro_ros/stage7_arm.meta')
 for name in required:
  if not (ROOT/name).is_file():issues.append(f"Missing recovered project input: {name}")
 return issues

def rosenv():
 identity();e=ros_environment()
 e.update(PYTHONUNBUFFERED='1',CMAKE_BUILD_PARALLEL_LEVEL='4');return e
def record(name,data):
 p=OUT/(name+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')
def run(name,cmd,env=None,timeout=600,cwd=WS):
 identity();folder=WS/'runs';folder.mkdir(exist_ok=True);path=folder/(name+'-'+str(time.monotonic_ns())+'.log')
 with path.open('w') as log:
  log.write('$ '+' '.join(map(str,cmd))+'\n');log.flush();p=subprocess.Popen(list(map(str,cmd)),cwd=cwd,env=env or rosenv(),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)
   rc=124
 print(name,rc,str(path),flush=True)
 if rc:print(path.read_text()[-6500:],flush=True)
 return rc,path
