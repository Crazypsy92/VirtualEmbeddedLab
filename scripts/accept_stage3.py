#!/usr/bin/env python3
"""Final Stage 3 acceptance: real builds, old matrix, new Cortex-M3 tests, immutable gates."""
from vel_env import tool_environment
import argparse,datetime,json,os,pathlib,subprocess,sys,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]; OUT=pathlib.Path(os.environ.get('VEL_STAGE3_EVIDENCE',str(ROOT/'evidence/stage3'))); OUT.mkdir(parents=True,exist_ok=True)
ap=argparse.ArgumentParser(); ap.add_argument('--test-only',action='store_true'); args=ap.parse_args()
env=tool_environment(); env['VEL_STAGE2_EVIDENCE']=str(OUT/'regression')
results={}; counts={}; archived_gates={}
def publish(state):
    (OUT/'acceptance.json').write_text(json.dumps({'timestamp':datetime.datetime.now().astimezone().isoformat(),'baseline':'4b229b2','overall':state,'results':results,'archived_gates':archived_gates,'ctest_counts':counts,'qemu':'PASS' if state=='Stage 3 SOFTWARE PASS' else state,'hardware':'NOT TESTED'},indent=2)+'\n')
publish('IN_PROGRESS')
def run(name,cmd,timeout=240):
    print('RUN '+name,flush=True)
    try:
        r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout); text=r.stdout; rc=r.returncode
    except (OSError,subprocess.TimeoutExpired) as e: text=str(e); rc=1
    (OUT/(name+'.log')).write_text('$ '+' '.join(map(str,cmd))+'\n'+text+'\nexit='+str(rc)+'\n'); results[name]=rc
    print(name+(' PASS' if rc==0 else ' FAIL'),flush=True)
    if rc: print(text[-6000:])
    return rc
cmd=[sys.executable,'scripts/accept_stage2.py']+(['--test-only'] if args.test_only else [])
if not run('historical_regression',cmd):
    x=json.loads((OUT/'regression/acceptance.json').read_text()); counts.update(x['ctest_counts'])
    if x['overall']!='Stage 2 SOFTWARE PASS': results['historical_regression']=1
else:
    publish('FAIL'); sys.exit(1)
run('freertos_ctest',['ctest','--test-dir',str(ROOT/'build/freertos'),'-V','--output-junit',str(OUT/'freertos_ctest.xml')],120)
x=ET.parse(OUT/'freertos_ctest.xml').getroot(); counts['freertos']={k:int(x.attrib.get(k,'0')) for k in ['tests','failures','disabled']}
if int(x.attrib['tests'])!=14 or int(x.attrib.get('failures','0')) or int(x.attrib.get('disabled','0')): results['freertos_ctest']=1
for stage,expected in [('stage3_1',3),('stage3_2',5)]:
    archived=ROOT/'evidence/stage3'/stage/'gate.xml'
    if not archived.is_file():
        archived_gates[stage]='ARCHIVE NOT RECOVERED'
        continue
    gate=ET.parse(archived).getroot()
    results[stage+'_gate']=0 if int(gate.attrib['tests'])==expected and int(gate.attrib.get('failures','0'))==0 else 1
    archived_gates[stage]='PASS' if results[stage+'_gate']==0 else 'FAIL'
publish('Stage 3 SOFTWARE PASS' if not any(results.values()) else 'FAIL')
print((OUT/'acceptance.json').read_text()); sys.exit(bool(any(results.values())))
