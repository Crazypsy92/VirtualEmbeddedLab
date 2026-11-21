#!/usr/bin/env python3
"""Stage 2 matrix, baseline regressions and demo, with fail-closed evidence."""
from vel_env import tool_environment
import argparse,datetime,json,os,pathlib,shlex,subprocess,sys,tempfile,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path(os.environ.get('VEL_STAGE2_EVIDENCE',str(ROOT/'evidence/stage2')))
OUT.mkdir(parents=True,exist_ok=True)
ap=argparse.ArgumentParser(); ap.add_argument('--test-only',action='store_true'); a=ap.parse_args()
env=tool_environment()
env['VEL_STAGE1_EVIDENCE']=str(OUT/'regression')
env['VEL_STAGE0_EVIDENCE']=str(OUT/'stage0_regression')
env['ASAN_OPTIONS']='detect_leaks=1:halt_on_error=1:abort_on_error=1'
env['UBSAN_OPTIONS']='halt_on_error=1:print_stacktrace=1'
results={}; counts={}
(OUT/'acceptance.json').write_text(json.dumps({'overall':'IN_PROGRESS','timestamp':datetime.datetime.now().astimezone().isoformat()})+'\n')
def run(name,cmd,timeout=120):
    print('RUN '+name+': '+shlex.join(map(str,cmd)),flush=True)
    try:
        r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        text=r.stdout; rc=r.returncode
    except (OSError,subprocess.TimeoutExpired) as e: text=str(e); rc=1
    (OUT/(name+'.log')).write_text('$ '+shlex.join(map(str,cmd))+'\n'+text+'\nexit='+str(rc)+'\n')
    results[name]=rc
    print(name+(' PASS' if rc==0 else ' FAIL'),flush=True)
    if rc: print(text[-8000:])
    return rc
def publish():
    summary={'timestamp':datetime.datetime.now().astimezone().isoformat(),'baseline':'3069747','results':results,'ctest_counts':counts,'overall':'Stage 2 SOFTWARE PASS' if not any(results.values()) else 'FAIL','fatfs_qemu':'NOT IMPLEMENTED','hardware':'NOT TESTED'}
    (OUT/'acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if not a.test_only:
    if run('matrix_build',[sys.executable,'scripts/build.py','all'],240):
        publish(); sys.exit(1)
for target,folder in [('debug','host'),('release','host-release'),('sanitize','host-sanitize'),('arm','arm')]:
    rc=run(target+'_ctest',['ctest','--test-dir',str(ROOT/'build'/folder),'-V','--output-junit',str(OUT/(target+'_ctest.xml'))],120)
    file=OUT/(target+'_ctest.xml')
    if file.exists():
        x=ET.parse(file).getroot(); counts[target]={k:int(x.attrib.get(k,'0')) for k in ['tests','failures','disabled']}
        if counts[target]['tests']==0: results[target+'_ctest']=1
run('stage0_regression',[sys.executable,'scripts/stage0.py'])
run('host_original_regression',['ctest','--test-dir',str(ROOT/'build/host'),'-R','^host_smoke$','-V'])
run('provenance',[sys.executable,'scripts/verify_fatfs.py'])
with tempfile.TemporaryDirectory(prefix='demo-',dir=ROOT/'build') as tmp:
    demo=ROOT/'build/host/fatfs_demo'
    run('demo_create',[str(demo),'--create-new-and-format',tmp])
    before=(pathlib.Path(tmp)/'sdcard.img').read_bytes()
    run('demo_reopen',[str(demo),'--read-only',tmp])
    print('RUN demo_refuse_existing',flush=True)
    r=subprocess.run([str(demo),'--create-new-and-format',tmp],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
    unchanged=(pathlib.Path(tmp)/'sdcard.img').read_bytes()==before
    results['demo_refuse_existing']=0 if r.returncode!=0 and unchanged else 1
    (OUT/'demo_refuse_existing.log').write_text(r.stdout+'\nexit='+str(r.returncode)+'\nimage_unchanged='+str(unchanged)+'\n')
# Prove the storage, FatFs and port objects are instrumented, not just a test launcher.
if run('sanitizer_symbols',['nm',str(ROOT/'build/host-sanitize/fatfs_tests')])==0:
    text=(OUT/'sanitizer_symbols.log').read_text()
    if '__asan_init' not in text or '__ubsan_handle' not in text: results['sanitizer_symbols']=1
# Distinct original test count is retained; ARM unchanged at six tests.
if counts.get('arm',{}).get('tests')!=6: results['arm_ctest']=1
publish()
sys.exit(bool(any(results.values())))
