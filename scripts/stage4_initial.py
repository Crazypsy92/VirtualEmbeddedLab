from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage4_support import *
import re,json
for name,source in [('hello','samples/hello_world'),('sync','samples/synchronization')]:
    rc,_=build('stage4_1/'+name,source)
    if rc: raise SystemExit(rc)
    cmd=[sys.executable,'-m','west','build','-d',ROOT/'build/zephyr'/name,'-t','run']
    if name=='hello': predicate=lambda text:'Hello World!' in text
    else: predicate=lambda text:len(re.findall('Hello World',text))>=4 and 'thread_a' in text and 'thread_b' in text
    rc,text,reached,expired=run('stage4_1/'+name+'_official_run',cmd,predicate,20,cwd=zephyr_base())
    if not reached or expired: raise SystemExit(1)
rc,_=build('stage4_1/kernel',ROOT/'zephyr/apps/kernel_demo')
if rc: raise SystemExit(rc)
rc,text,_,expired=run('stage4_1/kernel',qemu(ROOT/'build/zephyr/kernel/zephyr/zephyr.elf'))
z={k:int(v) for k,v in re.findall(r'\[STAT\] (\w+)=(\d+)',text)}
assert not expired and rc==0 and z['worker_a']==8 and z['worker_b']==8 and z['preemption']==1 and z['timer']>1 and z['work']==1 and z['result']==0 and '[ERROR]' not in text
print('OFFICIAL_AND_KERNEL_QEMU_PASS')
