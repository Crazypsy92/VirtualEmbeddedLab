from stage7_support import *
import sys
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='regression-',dir=WS/'runs'));env=os.environ.copy();env['VEL_STAGE6_EVIDENCE']=str(d/'stage6')
rc,log=run('historical_123',[sys.executable,ROOT/'scripts/accept_stage6.py'],env,3000)
if rc:record('regression/summary',{'status':'FAIL','exit':rc,'log':str(log)});raise SystemExit(rc)
a=json.loads((d/'stage6/acceptance.json').read_text());counts=a['ctest_counts'];assert sum(c['tests'] for c in counts.values())==123 and all(c['failures']==c['disabled']==0 for c in counts.values())
record('regression/summary',{'status':'PASS','historical_total':123,'counts':counts,'external_logs':str(d),'log':str(log),'historical_evidence_preserved':True});print('REGRESSION_123_PASS')
