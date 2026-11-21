#!/usr/bin/env python3
from stage4_support import *
import json,datetime,sys,xml.etree.ElementTree as ET
OUT.mkdir(parents=True,exist_ok=True)
results={}; counts={}
def publish(status):
    (OUT/'acceptance.json').write_text(json.dumps({'timestamp':datetime.datetime.now().astimezone().isoformat(),'baseline':'3dead0e','overall':status,'results':results,'ctest_counts':counts,'hardware':'NOT TESTED','stage5':'NOT IMPLEMENTED'},indent=2)+'\n')
def step(name,cmd,timeout=300):
    rc,_=call(name,cmd,timeout=timeout); results[name]=rc
    if rc: publish('FAIL'); raise SystemExit(1)
publish('IN_PROGRESS')
step('environment_check',[sys.executable,'scripts/stage4_case.py','environment'])
step('stage4_1/build_and_examples',[sys.executable,'scripts/stage4_initial.py'],300)
step('stage4_1/gdb_check',[sys.executable,'scripts/gdb_stage4.py','kernel'])
env=environment(); env['VEL_STAGE3_EVIDENCE']=str(OUT/'regression')
r=subprocess.run([sys.executable,'scripts/accept_stage3.py'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
(OUT/'regression_run.log').write_text('$ python3 scripts/accept_stage3.py (VEL_STAGE3_EVIDENCE=stage4/regression)\n'+r.stdout+'\nexit='+str(r.returncode)+'\n'); results['regression']=r.returncode
if r.returncode: publish('FAIL'); raise SystemExit(1)
old=json.loads((OUT/'regression/acceptance.json').read_text()); assert old['overall']=='Stage 3 SOFTWARE PASS'; counts.update(old['ctest_counts'])
(OUT/'stage4_1/gate.json').write_text(json.dumps({'status':'PASS','official_examples':True,'kernel':True,'gdb':True,'historical_tests':80},indent=2)+'\n')
step('stage4_2/build_and_tests',[sys.executable,'scripts/stage4_sensor.py'],300)
step('stage4_2/gdb_check',[sys.executable,'scripts/gdb_stage4.py','sensor'])
(OUT/'stage4_2/gate.json').write_text(json.dumps({'status':'PASS','sensor_api':True,'instances':2,'concurrent_fetches':80,'kconfig_disabled_run':True,'required_property_rejected':True},indent=2)+'\n')
step('stage4_3/build_and_tests',[sys.executable,'scripts/stage4_acquisition.py'],500)
step('test_configure',['cmake','-S','zephyr/tests','-B','build/zephyr-tests'])
step('ctest',['ctest','--test-dir','build/zephyr-tests','-V','--output-junit',str(OUT/'ctest.xml')],300)
x=ET.parse(OUT/'ctest.xml').getroot(); counts['zephyr']={k:int(x.attrib.get(k,'0')) for k in ['tests','failures','disabled']}
if x.findall('.//failure') or x.findall('.//skipped') or int(x.attrib['tests'])!=18: publish('FAIL'); raise SystemExit(1)
publish('Stage 4 SOFTWARE PASS · QEMU PASS'); print((OUT/'acceptance.json').read_text())
