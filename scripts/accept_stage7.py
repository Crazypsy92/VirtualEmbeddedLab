#!/usr/bin/env python3
"""Ordered, fail-closed Stage7 acceptance; all raw logs stay outside the Git repository."""
from stage7_support import *
from stage6_support import micro_ros_blockers
import sys,datetime,xml.etree.ElementTree as ET,hashlib,fcntl
identity();WS.mkdir(exist_ok=True);(WS/'runs').mkdir(exist_ok=True)
lock=(WS/'accept.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
d=pathlib.Path(tempfile.mkdtemp(prefix='accept-',dir=WS/'runs'));steps={};counts={};started=time.time()
def publish(status):
 record('acceptance',{'status':status,'timestamp':datetime.datetime.now().astimezone().isoformat(),'baseline':'7ad467e','workspace':str(WS),'steps':steps,'ctest_counts':counts,'external_logs':str(d),'hardware':'NOT TESTED','stage8':'NOT IMPLEMENTED'})
def step(name,cmd,timeout=600):
 rc,log=run(name,cmd,timeout=timeout);steps[name]={'exit':rc,'log':str(log),'command':list(map(str,cmd))};publish('IN_PROGRESS' if rc==0 else 'FAIL')
 if rc:raise SystemExit(rc)
def tests(label):
 xml=d/(label+'.xml');step('ctest_'+label,['ctest','--test-dir','build/stage7-tests','-L',label,'-j','1','--stop-on-failure','-V','--output-junit',xml],1200)
 root=ET.parse(xml).getroot();c={k:int(root.attrib.get(k,'0')) for k in ['tests','failures','disabled']};assert c['tests']>0 and c['failures']==c['disabled']==0;counts[label]=c;publish('IN_PROGRESS')
blockers=micro_ros_blockers(7)
if blockers:
 steps['prerequisites']={'status':'BLOCKED','reasons':blockers}
 publish('BLOCKED')
 print('\n'.join(blockers))
 raise SystemExit(2)
publish('IN_PROGRESS')
step('environment',['/usr/bin/python3',ROOT/'scripts/stage7_environment.py'])
for script in ['stage7_build_host_interfaces','stage7_build_libs','stage7_build']:
 step(script,['/usr/bin/python3',ROOT/'scripts'/(script+'.py')],900)
step('configure',['cmake','-S','micro_ros/stage7_tests','-B','build/stage7-tests','-DPython3_EXECUTABLE=/usr/bin/python3'])
tests('baseline')
step('optimized_build',['/usr/bin/python3',ROOT/'scripts/stage7_build.py','--optimized'],600)
tests('optimized');tests('resource')
step('historical_123',['/usr/bin/python3',ROOT/'scripts/stage7_regression.py'],3100)
reg=json.loads((OUT/'regression/summary.json').read_text());assert reg['historical_total']==123 and reg['status']=='PASS';counts.update({'historical_'+k:v for k,v in reg['counts'].items()})
step('preserve_history',['/usr/bin/python3',ROOT/'scripts/stage7_environment.py'])
for name in ['stage7_1/recovery_gate','stage7_1/optimized_recovery','stage7_2/stress','stage7_2/faults','stage7_2/gdb','stage7_2/optimized_stress','stage7_2/optimized_faults','stage7_2/optimized_gdb','stage7_3/memory']:
 p=OUT/(name+'.json');assert p.stat().st_mtime>=started and json.loads(p.read_text())['status']=='PASS',name
files=set(WS.rglob('*.log'))|set(d.glob('*.xml'))|set(WS.rglob('process_exits.json'))
# Include the nested historical acceptance manifest, whose own raw files remain outside Git.
record('log_manifest',{'files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files) if p.is_file() and p.name!='accept-latest.log'],'historical_manifest':str(pathlib.Path(reg['external_logs'])/'stage6/log_manifest.json')})
publish('Stage 7 SOFTWARE PASS · micro-ROS RECOVERY PASS · QEMU PASS');print(json.dumps(json.loads((OUT/'acceptance.json').read_text()),indent=2))
