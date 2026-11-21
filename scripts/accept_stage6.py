#!/usr/bin/env python3
"""Run the ordered real micro-ROS gates, then preserve all 108 historical tests."""
from stage6_support import *
import sys,xml.etree.ElementTree as ET,datetime,hashlib
identity();directory=pathlib.Path(tempfile.mkdtemp(prefix='accept-',dir=WS/'runs'));steps={};counts={};started=time.time()
def publish(status):
 record('acceptance',{'timestamp':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'baseline':'e415aa8','overall':status,'user':pwd.getpwuid(os.getuid()).pw_name,'home':os.environ['HOME'],'workspace':str(WS),'steps':steps,'ctest_counts':counts,'external_logs':str(directory),'hardware':'NOT TESTED','stage7':'NOT IMPLEMENTED'})
def step(name,command,timeout=600):
 rc,path=run(name,command,os.environ.copy(),timeout,ROOT);steps[name]={'exit':rc,'command':list(map(str,command)),'external_log':str(path)};publish('IN_PROGRESS' if rc==0 else 'FAIL')
 if rc:raise SystemExit(rc)
blockers=micro_ros_blockers(6)
if blockers:
 steps['prerequisites']={'status':'BLOCKED','reasons':blockers}
 publish('BLOCKED')
 print('\n'.join(blockers))
 raise SystemExit(2)
publish('IN_PROGRESS')
step('configure',['cmake','-S','micro_ros/tests','-B','build/stage6-tests','-DPython3_EXECUTABLE=/usr/bin/python3'])
step('stage6_ctest',['ctest','--test-dir','build/stage6-tests','--stop-on-failure','-j','1','-V','--output-junit',directory/'stage6_ctest.xml'],2400)
x=ET.parse(directory/'stage6_ctest.xml').getroot();counts['stage6']={k:int(x.attrib.get(k,'0')) for k in ['tests','failures','disabled']};assert counts['stage6']['tests']>0 and counts['stage6']['failures']==counts['stage6']['disabled']==0
for name in ['versions','stage6_1/build_gate','stage6_1/host_gate','stage6_2/dev_tools','stage6_2/newlib','stage6_2/toolchain_prepare','stage6_2/arm_libraries','stage6_2/firmware_build','stage6_2/runtime_gate','stage6_2/gdb_gate','stage6_3/interfaces','stage6_3/firmware_build','stage6_3/e2e_gate','stage6_3/fault_gate','memory']:
 p=OUT/(name+'.json');assert p.stat().st_mtime>=started and json.loads(p.read_text())['status']=='PASS',name
step('historical_108',[sys.executable,ROOT/'scripts/stage6_regression.py'],1200)
regression=json.loads((OUT/'regression/summary.json').read_text());assert regression['historical_total']==108 and regression['status']=='PASS';counts.update(regression['counts'])
files=set(directory.rglob('*.xml'))
for p in (WS/'runs').rglob('*.log'):files.add(p)
# Record latest Stage5 regression runtime logs too, without copying runtime data into Git.
legacy=pathlib.Path(json.loads((pathlib.Path(regression['external_logs'])/'stage5/acceptance.json').read_text())['external_logs'])
files.update(legacy.rglob('*.log'));files.update(legacy.rglob('*.xml'))
record('log_manifest',{'external_files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files) if p.is_file()]})
publish('Stage 6 SOFTWARE PASS · micro-ROS ↔ QEMU PASS · HARDWARE NOT TESTED')
print(json.dumps(json.loads((OUT/'acceptance.json').read_text()),indent=2),flush=True)
