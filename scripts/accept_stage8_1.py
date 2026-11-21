#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage8_1_support import *
import argparse,sys
ap=argparse.ArgumentParser();ap.add_argument('--backend',choices=['all','qemu','native_sim','renode'],default='all');args=ap.parse_args();results={}
nonroot()
if args.backend in ('native_sim','renode'):
 os.environ['VEL_STAGE8_1_LOCAL_ONLY']='1'
for backend in (['qemu','native_sim','renode'] if args.backend=='all' else [args.backend]):
 try:
  if backend=='qemu':
   env=tool_environment();env['VEL_STAGE7_EVIDENCE']=str(WS/'regression/stage7');p=run('qemu_regression',['/usr/bin/python3',ROOT/'scripts/accept_stage7.py'],4200,env);gate();a=json.loads((WS/'regression/stage7/acceptance.json').read_text());results[backend]=dict(p,status='PASS' if p['exit']==0 else 'FAIL',tests=sum(c['tests'] for c in a['ctest_counts'].values()),target='mps2-an385 / Cortex-M3');record('qemu/acceptance',results[backend])
  else:
   gate()
   if backend=='renode':
    install=run('renode_install',['/usr/bin/python3',ROOT/'scripts/stage8_1_install_renode.py'],360)
    if install['exit']:raise RuntimeError('Renode install failed: '+install['log'])
   p=run(backend,['/usr/bin/python3',ROOT/'scripts'/('stage8_1_'+('native' if backend=='native_sim' else 'renode')+'.py')],600)
   detail=json.loads((OUT/backend/'acceptance.json').read_text()) if (OUT/backend/'acceptance.json').exists() else {};results[backend]=dict(detail,**p);results[backend]['status']='PASS' if p['exit']==0 else 'FAIL'
 except Exception as e:results[backend]={'status':'FAIL','error':repr(e)}
 record('acceptance',{'backends':results,'hardware':'NOT TESTED','stage8_2':'NOT IMPLEMENTED'})
print(json.dumps(results,indent=2));raise SystemExit(any(r['status']!='PASS' for r in results.values()))
