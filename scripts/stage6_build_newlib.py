#!/usr/bin/env python3
from stage6_support import *
import urllib.request,tarfile,hashlib
identity();assert json.loads((OUT/'stage6_1/host_gate.json').read_text())['status']=='PASS'
version='4.4.0';commit='26f7004bf73c421c3fd5e5a6ccf470d05337b435';url='https://codeload.github.com/mirror/newlib-cygwin/tar.gz/'+commit;archive=WS/'downloads'/('newlib-'+commit+'.tar.gz')
if not archive.exists():
 rc,log=run('newlib_download',['curl','--fail','--location','--connect-timeout','15','--max-time','90','--output',archive,url],os.environ.copy(),100)
 if rc:raise SystemExit(rc)
source=WS/'sources'/'newlib-private'
if not source.exists():
 staging=WS/'sources'/'newlib-extract';staging.mkdir(exist_ok=True)
 with tarfile.open(archive) as tar:tar.extractall(staging,filter='data')
 children=list(staging.iterdir());assert len(children)==1;children[0].rename(source);staging.rmdir()
header=source/'newlib/libc/include/_newlib_version.h'
assert header.is_file()  # Git checkout contains a dummy; configure generates version header.
lock=ROOT/'micro_ros/dependencies.lock.json';data=json.loads(lock.read_text());digest=hashlib.sha256(archive.read_bytes()).hexdigest()
if data.get('newlib',{}).get('archive_sha256'):assert data['newlib']['archive_sha256']==digest
data['newlib']={'repository':'https://sourceware.org/git/newlib-cygwin.git','mirror':'https://github.com/mirror/newlib-cygwin','requested_ref':'newlib-4.4.0','commit':commit,'release':version,'archive_url':url,'archive_sha256':digest,'verification':'commit resolved from annotated Git tag, fixed commit archive SHA256; official release archive download stalled and was stopped'};lock.write_text(json.dumps(data,indent=2)+'\n')
build=WS/'newlib_build';build.mkdir(exist_ok=True);env=os.environ.copy();env.update(CFLAGS_FOR_TARGET='-mcpu=cortex-m3 -mthumb -Os -g -ffunction-sections -fdata-sections',CXXFLAGS_FOR_TARGET='-mcpu=cortex-m3 -mthumb -Os')
for name,cmd in [('newlib_configure',[source/'configure','--target=arm-none-eabi','--prefix='+str(WS/'newlib_install'),'--disable-multilib','--disable-nls','--enable-newlib-retargetable-locking','--disable-newlib-supplied-syscalls']),('newlib_build',['make','-j4','all-target-newlib']),('newlib_install',['make','install-target-newlib'])]:
 rc,log=run(name,cmd,env,600,build)
 if rc:record('stage6_2/newlib',{'status':'FAIL','step':name,'external_log':str(log)});raise SystemExit(rc)
header=WS/'newlib_install/arm-none-eabi/include/newlib.h';assert '#define _RETARGETABLE_LOCKING 1' in header.read_text()
multi=subprocess.check_output(['arm-none-eabi-gcc','-mcpu=cortex-m3','-mthumb','--print-multi-directory'],text=True).strip()
for name in ['libc.a','libm.a','libg.a']:
 target=WS/'newlib_install/arm-none-eabi/lib'/multi/name;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():target.symlink_to(WS/'newlib_install/arm-none-eabi/lib'/name)
record('stage6_2/newlib',{'status':'PASS','version':version,'retargetable_locking':True,'cpu':'cortex-m3 Thumb','prefix':str(WS/'newlib_install/arm-none-eabi'),'not_system_install':True})
