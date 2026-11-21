from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage7_support import *
import re,hashlib,shlex,collections
for name in ['stage7_2/optimized_stress','stage7_2/optimized_faults','stage7_2/optimized_gdb','stage7_1/optimized_recovery']:
 assert json.loads((OUT/(name+'.json')).read_text())['status']=='PASS',name
profiles={}
for kind in ['baseline','optimized']:
 b=WS/(kind+'_build');z=b/'zephyr';elf=z/'zephyr.elf';size=subprocess.check_output(['arm-none-eabi-size','-A',elf],text=True);symbols=subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',elf],text=True)
 (z/'stage7_sections.txt').write_text(size);(z/'stage7_symbols.txt').write_text(symbols);sections={};rom=ram=0;top=0
 for line in size.splitlines():
  f=line.split()
  if len(f)==3 and f[1].isdigit() and f[2].isdigit():
   n,a=int(f[1]),int(f[2]);sections[f[0]]={'size':n,'address':a}
   if 0x20000000<=a<0x20400000:ram+=n;top=max(top,a+n)
   elif a<0x400000 and not f[0].startswith(('.debug','.comment','.ARM.attributes')):rom+=n
 pools={}
 for line in symbols.splitlines():
  f=line.split()
  if len(f)==4 and (f[3].startswith('custom_') or any(t in f[3] for t in ['stack','heap','rx_ring'])):pools[f[3]]=int(f[1],16)
 # Only allocated input sections after the actual Linker script marker. Exclude discarded input sections.
 text=(z/'zephyr.map').read_text().split('Linker script and memory map',1)[1];groups=collections.defaultdict(lambda:dict(rom=0,ram=0));pending=''
 for line in text.splitlines():
  secmatch=re.match(r' +(\.[^ ]+)',line)
  if secmatch:pending=secmatch[1].strip()
  if pending.startswith(('.debug','.comment','.ARM.attributes')):continue
  m=re.match(r' +(?:\.[^ ]+ +)?(0x[0-9a-f]+) +(0x[0-9a-f]+) +(.+\.(?:a\([^)]*\)|obj))$',line)
  if not m:continue
  address,length=int(m[1],16),int(m[2],16);obj=m[3]
  if not (address<0x400000 or 0x20000000<=address<0x20400000):continue
  group='other'
  for token,title in [('vel_virtual_sensor','Sensor driver'),('main.c.obj','Application + UART transport'),('libkernel.a','Zephyr Kernel'),('librmw_micro','RMW'),('libmicroxrcedds','XRCE client'),('librclc.a','RCLC'),('librcl.a','RCL'),('libc.a','Newlib'),('libm.a','Newlib math'),('libgcc.a','compiler runtime')]:
   if token in obj:group=title;break
  else:
   if 'zephyr/' in obj:group='Zephyr other'
   elif '/arm_install/' in obj:group='ROS types/runtime + MicroCDR'
  groups[group]['ram' if address>=0x20000000 else 'rom']+=length
 profiles[kind]={'rom_sections_bytes':rom,'bin_bytes':(z/'zephyr.bin').stat().st_size,'ram_sections_bytes':ram,'ram_span_bytes':top-0x20000000,'sections':sections,'fixed_newlib_arena_bytes':8192 if kind=='optimized' else None,'pools_and_stacks':pools,'allocated_input_groups':dict(groups),'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'artifacts':{ext:str(z/('zephyr.'+ext)) for ext in ['elf','bin','map']},'section_log':str(z/'stage7_sections.txt'),'symbol_log':str(z/'stage7_symbols.txt')}
# Debug symbols have no runtime address cost; measure a real stripped artifact separately.
 elf=WS/(kind+'_build')/'zephyr/zephyr.elf';stripped=elf.with_name('zephyr.stripped.elf')
 subprocess.run(['arm-none-eabi-objcopy','--strip-debug',elf,stripped],check=True,timeout=15)
 profiles[kind]['debug_symbols']={'elf_bytes':elf.stat().st_size,'stripped_elf_bytes':stripped.stat().st_size,'allocated_size_before':subprocess.check_output(['arm-none-eabi-size',elf],text=True).splitlines()[-1].split()[:3],'allocated_size_after':subprocess.check_output(['arm-none-eabi-size',stripped],text=True).splitlines()[-1].split()[:3]}
 assert profiles[kind]['debug_symbols']['allocated_size_before']==profiles[kind]['debug_symbols']['allocated_size_after']
# A separate resource-only relink uses a strict 512 KiB / 64 KiB MEMORY block.
# Peripheral addresses and AN385 startup remain unchanged: this is never an STM32 BSP.
budget_checks={}
for kind in ['baseline','optimized']:
 b=WS/(kind+'_build');d=WS/('stm32_budget_'+kind);d.mkdir(exist_ok=True);lds=(b/'zephyr/linker.cmd').read_text();lds=lds.replace('LENGTH = (4096 * 1024 - 0x0 - 0x0)','LENGTH = (512 * 1024 - 0x0 - 0x0)').replace('LENGTH = (4096 * 1K)','LENGTH = (64 * 1K)');assert 'LENGTH = (64 * 1K)' in lds
 (d/'budget.ld').write_text(lds)
 line=subprocess.check_output(['ninja','-t','commands','zephyr/zephyr.elf'],cwd=b,text=True).splitlines()[-1];parts=shlex.split(line);start=next(i for i,arg in enumerate(parts) if Path(arg).name=='arm-none-eabi-gcc');end=parts.index('&&',start) if '&&' in parts[start:] else len(parts);cmd=parts[start:end]
 cmd[cmd.index('-o')+1]=str(d/'budget.elf');cmd[cmd.index('-T')+1]=str(d/'budget.ld')
 cmd=[('-Wl,-Map,'+str(d/'budget.map')) if c.startswith('-Wl,-Map,') else c for c in cmd]
 rc,log=run('stm32_budget_link',cmd,timeout=60,cwd=b);fit=rc==0
 if not fit:assert 'overflowed' in log.read_text() or 'will not fit' in log.read_text(),log.read_text()
 budget_checks[kind]={'result':'FIT' if fit else 'NOT FIT','link_exit':rc,'log':str(log),'linker_script':str(d/'budget.ld')}
base=profiles['baseline'];opt=profiles['optimized'];assert opt['ram_span_bytes']<base['ram_span_bytes'] and opt['rom_sections_bytes']<base['rom_sections_bytes']
runtime={}
for prefix,stack in [('',16384),('optimized_',6144)]:
 samples=[];stacks=[];live=[];cleaned=[]
 for name in ['stage7_1/'+('optimized_recovery' if prefix else 'recovery_gate'),'stage7_2/'+prefix+'stress','stage7_2/'+prefix+'faults','stage7_2/'+prefix+'gdb']:
  v=json.loads((OUT/(name+'.json')).read_text());cases=v.get('cases',v.get('paths',[v]))
  for case in cases:
   samples+=case['memory'];cleaned+=case['cleaned'];p=case['peer']
   if p.get('stack_unused_min_sampled',2**32-1)<2**32-1:stacks.append(p['stack_unused_min_sampled']);live.append(p.get('heap_live_peak_sampled',0))
 stacks += [m['unused'] for m in samples];assert min(stacks)>0
 runtime[prefix or 'baseline']={'stack_reserved':stack,'stack_used_max_observed':stack-min(stacks),'stack_unused_min_observed':min(stacks),'newlib_arena_exact_peak':max(m['arena_peak'] for m in samples),'newlib_live_max_sampled':max(live or [0]),'all_cleanup_live_zero':all(m['live']==0 for m in cleaned)}
record('stage7_3/memory',{'status':'PASS','profiles':profiles,'runtime':runtime,'reduction':{'rom_bytes':base['rom_sections_bytes']-opt['rom_sections_bytes'],'ram_span_bytes':base['ram_span_bytes']-opt['ram_span_bytes']},'stm32_budget':{'profiles':budget_checks,'target':'STM32F103ZET6','flash':524288,'ram':65536,'result':'FIT' if fit else 'NOT FIT','link_exit':rc,'link_log':str(log),'linker_script':str(d/'budget.ld'),'hardware':'NOT TESTED'},'scope':'Allocated sections; groups exclude alignment padding. Stack high water observed, live heap sampled; Newlib arena peak exact. QEMU memory unchanged.'});print('MEMORY_PASS','FIT' if fit else 'NOT FIT',profiles['optimized']['ram_span_bytes'])
