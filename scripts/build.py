#!/usr/bin/env python3
"""Build selected target with reproducible command/output logs."""
from vel_env import tool_environment
import argparse
import os
import pathlib
import subprocess
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument('target',choices=['host','arm','host-release','host-sanitize','freertos','all'],default='all',nargs='?')
args=ap.parse_args()
for target in (['host','host-release','host-sanitize','arm','freertos'] if args.target == 'all' else [args.target]):
    out=pathlib.Path(os.environ.get('VEL_STAGE2_EVIDENCE',str(ROOT/'evidence/stage2')))/f'{target}_build.log'
    out.parent.mkdir(parents=True,exist_ok=True)
    preset=target if target in ['host-release','host-sanitize'] else target+'-debug'
    with out.open('w') as log:
        for cmd in [['cmake','--preset',preset],['cmake','--build','--preset',preset,'--parallel','4','--verbose']]:
            log.write('$ '+' '.join(cmd)+'\n'); log.flush()
            try:
                r=subprocess.run(cmd,cwd=ROOT,env=tool_environment(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
                log.write(r.stdout+'\nexit='+str(r.returncode)+'\n'); print(r.stdout,end='')
                if r.returncode: sys.exit(r.returncode)
            except (OSError,subprocess.TimeoutExpired) as e:
                log.write('ERROR: '+str(e)+'\n'); sys.exit(1)
