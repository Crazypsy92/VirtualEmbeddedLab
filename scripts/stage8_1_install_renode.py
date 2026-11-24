from stage8_1_support import *
import urllib.request,hashlib,tarfile
# Stable official portable distribution, isolated per-user install; no system package changes.
gate()
pin=json.loads((ROOT/'simulation/renode/package.lock.json').read_text())
version,url=pin['version'],pin['url']
archive=WS/('renode-'+version+'.tar.gz');target=WS/'tools/renode'/version
WS.mkdir(parents=True,exist_ok=True)
if not archive.exists() and (cached := os.environ.get("VEL_GUI_RENODE_CACHE")):
 import shutil
 shutil.copyfile(cached,archive)
if not archive.exists():
 part=archive.with_suffix('.partial');subprocess.run(['curl','-fL','--connect-timeout','15','--max-time','180','--retry','2',url,'-o',str(part)],check=True,timeout=220);part.replace(archive)
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
if sha!=pin['sha256']:
 raise SystemExit(f'Renode archive checksum mismatch: {archive}')
if not target.exists():
 target.mkdir(parents=True)
 with tarfile.open(archive) as t:t.extractall(target,filter='data')
executables=list(target.rglob('renode'));assert executables
p=run('renode_version',[executables[0],'--version'],60);record('renode/install',dict(p,status='PASS' if p['exit']==0 else 'FAIL',version=version,sha256=sha,executable=str(executables[0])))
raise SystemExit(p['exit'])
