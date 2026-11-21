from vel_env import zephyr_base
from stage7_support import *
import sys,hashlib
identity();assert sys.executable=='/usr/bin/python3';assert WS.stat().st_uid==os.getuid()
subprocess.run(['git','merge-base','--is-ancestor','7ad467e','HEAD'],cwd=ROOT,check=True)
original=subprocess.check_output(['git','ls-tree','-r','--name-only','7ad467e'],cwd=ROOT,text=True).splitlines();protected=[p for p in original if p not in ['README.md','scripts/stage6_support.py','scripts/stage7_support.py','scripts/stage7_environment.py']]
subprocess.run(['git','diff','--exit-code','7ad467e','--',*protected],cwd=ROOT,check=True)
versions={}
for tool in ['gcc','arm-none-eabi-gcc','cmake','ninja','qemu-system-arm','gdb-multiarch','python3']:
 versions[tool]=subprocess.check_output([tool,'--version'],text=True).splitlines()[0]
assert 'mps2-an385' in subprocess.check_output(['qemu-system-arm','-M','help'],text=True)
zephyr=zephyr_base();zcommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=zephyr,text=True).strip();assert zcommit=='dccb09599635bdff17633fa7e9dab014b91dce90'
# Reuse the existing, exact archive/source verification logic with an external output directory.
env=os.environ.copy();env['VEL_STAGE6_EVIDENCE']=str(WS/'stage7_version_check');rc,log=run('pinned_sources',['/usr/bin/python3',ROOT/'scripts/stage6_versions.py'],env,120);assert rc==0
v=json.loads((WS/'stage7_version_check/versions.json').read_text())
record('environment',{'status':'PASS','baseline':'7ad467e','user':__import__('pwd').getpwuid(os.getuid()).pw_name,'HOME':os.environ['HOME'],'python':sys.executable,'versions':versions,'zephyr_commit':zcommit,'sources':v['dependencies'],'source_check_log':str(log),'protected_baseline_files':len(protected),'historical_evidence_unchanged':True,'workspace_owner_uid':WS.stat().st_uid})
print('ENVIRONMENT_PASS',len(protected))
