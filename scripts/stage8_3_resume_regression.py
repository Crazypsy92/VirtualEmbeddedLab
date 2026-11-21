from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
"""Resume only a failed Renode backend, retaining successful checks and original failures."""
import pathlib,json,subprocess,os,time,hashlib
R=pathlib.Path(__file__).resolve().parents[1];W=work('gateway_stage8_3_ws');O=R/'evidence/stage8_3'
old=json.loads((W/'regression/stage8_2/acceptance.json').read_text());assert old['status']=='FAIL'
for name in ['build','master','cleanup','resources']:assert old['steps'][name]['exit']==0
prior_path=work('modbus_stage8_2_ws') / 'regression/stage8_1/acceptance.json';prior=json.loads(prior_path.read_text());assert prior['backends']['qemu']['status']=='PASS' and prior['backends']['qemu']['tests']==133;assert prior['backends']['native_sim']['status']=='PASS'
env=os.environ.copy();env['VEL_STAGE8_1_EVIDENCE']=str(W/'recovery/renode');log=W/'runs'/('regression-recovery-'+str(time.monotonic_ns())+'.log');t=time.monotonic()
with log.open('w') as f:p=subprocess.run(['/usr/bin/python3',R/'scripts/accept_stage8_1.py','--backend','renode'],stdout=f,stderr=subprocess.STDOUT,env=env,timeout=180)
assert p.returncode==0,log
fresh=json.loads((W/'recovery/renode/acceptance.json').read_text())['backends']['renode'];assert fresh['status']=='PASS'
s8=json.loads((W/'regression/stage8_2/all/acceptance.json').read_text());cleanup=json.loads((W/'regression/stage8_2/fault/cleanup.json').read_text());assert s8['status']=='PASS' and cleanup['status']=='PASS'
counts={'stage0_7':prior['backends']['qemu']['tests'],'stage8_1_groups':prior['backends']['native_sim']['tests']+fresh['tests'],'new_groups':s8['tests']+1};assert counts=={'stage0_7':133,'stage8_1_groups':7,'new_groups':5}
d=O/'regression';d.mkdir(exist_ok=True);(d/'summary.json').write_text(json.dumps({'status':'PASS','counts':counts,'recovery':'Only failed Renode rerun; all successful results retained. Original failed commands were not rewritten.','original_stage8_2':old,'original_stage8_1':prior,'fresh_renode':fresh,'recovery_log':str(log)},indent=2)+'\n')
a=json.loads((O/'acceptance.json').read_text());(d/'original_failed_acceptance.json').write_text(json.dumps(a,indent=2)+'\n');a['steps']['regression_recovery']={'command':['/usr/bin/python3',str(R/'scripts/stage8_3_resume_regression.py')],'exit':0,'seconds':time.monotonic()-t,'log':str(log)};a['status']='Stage 8.3 SOFTWARE PASS';a['recovered_failure']='Original regression exit 1 retained; failed backend passed on rerun.';a['new_groups']=json.loads((O/'tests_all.json').read_text())['tests']+json.loads((O/'rtu/consistency.json').read_text())['tests'];(O/'acceptance.json').write_text(json.dumps(a,indent=2)+'\n')
files=[p for p in (W/'runs').rglob('*') if p.is_file() and p.name!='accept-latest.log'];(O/'log_manifest.json').write_text(json.dumps({'files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]},indent=2)+'\n');print('RECOVERED_REGRESSION_PASS',counts)
