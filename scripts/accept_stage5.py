#!/usr/bin/env python3
"""Real Stage 5 gates, then full 98-test historical regression. No network/install."""
from stage5_support import *
import sys,datetime,xml.etree.ElementTree as ET,hashlib
identity();run=pathlib.Path(tempfile.mkdtemp(prefix='accept-',dir=WS/'runs'));results={};counts={};started=time.time()
def publish(status):
    record('acceptance',{'timestamp':datetime.datetime.now().astimezone().isoformat(),'baseline':'1c0f5a0','overall':status,'results':results,'ctest_counts':counts,'external_logs':str(run),'user':pwd.getpwuid(os.getuid()).pw_name,'home':os.environ['HOME'],'workspace':str(WS),'hardware':'NOT TESTED','micro_ros_on_cortex_m3':'NOT INTEGRATED'})
def step(name,cmd,timeout=180,env=None):
    begin=time.monotonic();print(name,'RUNNING',flush=True)
    try:
        p=subprocess.Popen(list(map(str,cmd)),cwd=ROOT,env=env or os.environ.copy(),stdout=(run/(name+'.log')).open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        try:rc=p.wait(timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)
            rc=124
    except OSError as e:(run/(name+'.log')).write_text(str(e));rc=1
    results[name]={'exit':rc,'seconds':round(time.monotonic()-begin,2),'command':list(map(str,cmd))};publish('IN_PROGRESS' if rc==0 else 'FAIL')
    print(name,'PASS' if rc==0 else 'FAIL',flush=True)
    if rc:print((run/(name+'.log')).read_text()[-5000:]);raise SystemExit(rc)
publish('IN_PROGRESS')
step('configure',['cmake','-S','ros2/tests','-B','build/stage5-tests','-DPython3_EXECUTABLE=/usr/bin/python3'])
step('stage5_ctest',['ctest','--test-dir','build/stage5-tests','--stop-on-failure','-j','1','-V','--output-junit',run/'stage5_ctest.xml'],timeout=600)
x=ET.parse(run/'stage5_ctest.xml').getroot();counts['stage5']={k:int(x.attrib.get(k,'0')) for k in ['tests','failures','disabled']};assert counts['stage5']=={'tests':10,'failures':0,'disabled':0}
for gate in ['stage5_0/runtime_gate','stage5_1/host_mock_gate','stage5_2/build_gate','stage5_2/protocol_gate','stage5_2/uart_gate','stage5_3/e2e_gate','stage5_3/fault_gate','stage5_3/gdb_gate','memory']:
    file=OUT/(gate+'.json');assert file.stat().st_mtime>=started and json.loads(file.read_text())['status']=='PASS',gate
assert (ROOT/'docs/stage5_microros_feasibility.md').is_file(),'micro-ROS assessment required'
env=os.environ.copy();env['VEL_STAGE4_EVIDENCE']=str(run/'regression')
step('regression',[sys.executable,ROOT/'scripts/accept_stage4.py'],timeout=1000,env=env)
old=json.loads((run/'regression/acceptance.json').read_text());assert old['overall']=='Stage 4 SOFTWARE PASS · QEMU PASS',old
counts.update(old['ctest_counts']);historical=sum(v['tests'] for k,v in counts.items() if k!='stage5');assert historical==98
assert all(v['failures']==0 and v['disabled']==0 for v in counts.values())
record('regression/summary',{'status':'PASS','historical_total':historical,'counts':old['ctest_counts'],'external_logs':str(run/'regression'),'stage0_to4_evidence_preserved':True})
manifest=[]
# Keep raw runtime files and ROS logs outside Git; retain a small evidence index.
for base in [run]+[pathlib.Path(json.loads((OUT/(g+'.json')).read_text())['external_logs']) for g in ['stage5_0/runtime_gate','stage5_1/host_mock_gate','stage5_2/build_gate','stage5_2/protocol_gate','stage5_2/uart_gate','stage5_3/e2e_gate','stage5_3/fault_gate','stage5_3/gdb_gate','memory']]:
    for file in base.rglob('*'):
        if file.is_file() and file.suffix in ['.log','.xml']:
            manifest.append({'path':str(file),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
record('log_manifest',{'external_files':manifest})
publish('Stage 5 SOFTWARE PASS · ROS 2 ↔ QEMU PASS · HARDWARE NOT TESTED')
print(json.dumps(json.loads((OUT/'acceptance.json').read_text()),indent=2),flush=True)
