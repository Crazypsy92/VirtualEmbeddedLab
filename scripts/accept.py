#!/usr/bin/env python3
"""Final Host and ARM suites, recorded separately; fail closed on any failure."""
from vel_env import tool_environment
import datetime
import os
import json
import pathlib
import subprocess
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
if '--stage1-only' not in sys.argv:
    sys.exit(subprocess.run([sys.executable,str(ROOT/('scripts/accept_stage2.py' if '--stage2-only' in sys.argv else 'scripts/accept_stage3.py')),'--test-only'],cwd=ROOT).returncode)
out=pathlib.Path(os.environ.get('VEL_STAGE1_EVIDENCE', str(ROOT/'evidence/stage1')))
out.mkdir(parents=True,exist_ok=True)
results={}
for target in ['host','arm']:
    cmd=['ctest','--test-dir',str(ROOT/'build'/target),'--output-on-failure','--output-junit',str(out/(target+'_ctest.xml'))]
    if target=='host': cmd += ['-R','^host_smoke$']
    try:
        r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
        (out/(target+'_ctest.log')).write_text('$ '+' '.join(cmd)+'\n'+r.stdout+'\nexit='+str(r.returncode)+'\n')
        print(r.stdout,end='')
        results[target]=r.returncode
    except (OSError,subprocess.TimeoutExpired) as e:
        (out/(target+'_ctest.log')).write_text('FAILED: '+str(e)+'\n')
        results[target]=1
for name,cmd in [('elf_layout',[sys.executable,str(ROOT/'scripts/check_elf.py')])]:
    r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
    (out/(name+'.log')).write_text('$ '+' '.join(cmd)+'\n'+r.stdout+'\nexit='+str(r.returncode)+'\n')
    results[name]=r.returncode
(out/'acceptance.json').write_text(json.dumps({'timestamp':datetime.datetime.now().astimezone().isoformat(),'exit_codes':results,'overall':'PASS' if not any(results.values()) else 'FAIL'},indent=2)+'\n')
sys.exit(bool(any(results.values())))
