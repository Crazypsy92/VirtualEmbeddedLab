#!/usr/bin/env python3
from stage6_support import *
import sys
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='regression-',dir=WS/'runs'));env=os.environ.copy();env['VEL_STAGE5_EVIDENCE']=str(d/'stage5')
rc,path=run('historical_108',[sys.executable,ROOT/'scripts/accept_stage5.py'],env,1200,ROOT)
if rc:record('regression/summary',{'status':'FAIL','exit':rc,'external_log':str(path)});raise SystemExit(rc)
a=json.loads((d/'stage5/acceptance.json').read_text());counts=a['ctest_counts'];assert sum(v['tests'] for v in counts.values())==108 and all(v['failures']==v['disabled']==0 for v in counts.values())
record('regression/summary',{'status':'PASS','historical_total':108,'counts':counts,'external_logs':str(d),'external_log':str(path),'original_evidence_preserved':True})
print('HISTORICAL_108_PASS')
