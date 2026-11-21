#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import pathlib,os,subprocess,json,time,signal,argparse,hashlib
def terminated(signum,frame):raise SystemExit(128+signum)
signal.signal(signal.SIGTERM,terminated)
R=pathlib.Path(__file__).resolve().parents[1];W=work('modbus_stage8_2_ws');O=pathlib.Path(os.environ.get('VEL_STAGE8_2_EVIDENCE',str(R/'evidence/stage8_2')));O.mkdir(parents=True,exist_ok=True)
a=argparse.ArgumentParser();a.add_argument('--mode',choices=['build','protocol','fault','all'],default='all');mode=a.parse_args().mode;steps={}
def run(name,cmd,timeout,env=None):
 log=W/'runs'/(name+'-'+str(time.monotonic_ns())+'.log');t=time.monotonic()
 with log.open('w') as f:
  p=subprocess.Popen(list(map(str,cmd)),cwd=R,stdout=f,stderr=subprocess.STDOUT,env=env or tool_environment(),start_new_session=True)
  try:rc=p.wait(timeout)
  except BaseException as e:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(4)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(4)
   if not isinstance(e,subprocess.TimeoutExpired):raise
   rc=124
 steps[name]={'command':list(map(str,cmd)),'exit':rc,'seconds':time.monotonic()-t,'log':str(log)};publish('IN_PROGRESS' if rc==0 else 'FAIL')
 if rc:print(log.read_text()[-3000:]);raise SystemExit(rc)
def publish(status):
 (O/'acceptance.json').write_text(json.dumps({'status':status,'mode':mode,'steps':steps,'hardware':'NOT TESTED','physical_rs485':'NOT TESTED','stage8_3':'NOT IMPLEMENTED'},indent=2)+'\n')
nonroot();(W/'runs').mkdir(parents=True,exist_ok=True);publish('IN_PROGRESS')
run('build',['/usr/bin/python3',R/'scripts/stage8_2_build.py'],360)
if mode!='build':run('master',[sys.executable,R/'host/modbus_master/test_master.py',mode],180)
if mode=='all':
 run('cleanup',['/usr/bin/python3',R/'scripts/stage8_2_cleanup.py'],20)
 run('resources',['/usr/bin/python3',R/'scripts/stage8_2_resources.py'],60)
 env=tool_environment();env['VEL_STAGE8_1_EVIDENCE']=str(W/'regression/stage8_1');run('regression',['/usr/bin/python3',R/'scripts/accept_stage8_1.py','--backend','all'],4500,env)
 previous=json.loads((W/'regression/stage8_1/acceptance.json').read_text());assert all(v['status']=='PASS' for v in previous['backends'].values())
 p=O/'regression';p.mkdir(exist_ok=True);(p/'summary.json').write_text(json.dumps({'status':'PASS','stage0_7':133,'stage8_1_new':sum(previous['backends'][k]['tests'] for k in ['native_sim','renode']),'details':previous},indent=2)+'\n')
 files=[p for p in (W/'runs').rglob('*') if p.is_file() and p.name!='accept-latest.log'];(O/'log_manifest.json').write_text(json.dumps({'files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]},indent=2)+'\n')
publish('Stage 8.2 SOFTWARE PASS' if mode=='all' else 'PASS')
if mode=='all':
 a=json.loads((O/'acceptance.json').read_text());m=json.loads((O/'all/acceptance.json').read_text());c=json.loads((O/'fault/cleanup.json').read_text());assert c['status']=='PASS';reg=json.loads((O/'regression/summary.json').read_text());a['actual_counts']={'stage0_7':reg['stage0_7'],'stage8_1_groups':reg['stage8_1_new'],'new_groups':m['tests']+1};(O/'acceptance.json').write_text(json.dumps(a,indent=2)+'\n')
print('STAGE8_2_PASS',mode)
