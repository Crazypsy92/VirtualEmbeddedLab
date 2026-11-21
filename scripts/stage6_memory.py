#!/usr/bin/env python3
from stage6_support import *
import re,hashlib
identity();e=json.loads((OUT/'stage6_3/e2e_gate.json').read_text());assert e['status']=='PASS'
result={}
for name,folder in [('minimal',WS/'firmware_build/zephyr'),('acquisition',WS/'acquisition_build/zephyr')]:
 elf=folder/'zephyr.elf';text=subprocess.check_output(['arm-none-eabi-size','-A',elf],text=True);sections={}
 for line in text.splitlines():
  fields=line.split()
  if len(fields)==3 and fields[1].isdigit() and fields[2].isdigit():sections[fields[0]]={'size':int(fields[1]),'address':int(fields[2])}
 rom=ram=0;intervals=[]
 for sec,p in sections.items():
  a,n=p['address'],p['size']
  if 0x20000000<=a<0x20400000:
   ram+=n;assert a+n<=0x20400000
   if n:intervals.append((a,a+n))
  elif a<0x400000 and not sec.startswith(('.debug','.comment','.ARM.attributes')):rom+=n
 intervals.sort();assert all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:]));span=intervals[-1][1]-0x20000000
 assert rom<4194304 and span<4194304 and span>50000
 symbols=subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',elf],text=True);pools={}
 for line in symbols.splitlines():
  fields=line.split()
  if len(fields)==4 and (fields[3].startswith('custom_') or fields[3] in ['rx_ring','rx_ring_data']):pools[fields[3]]=int(fields[1],16)
 assert pools.get('custom_sessions',0)>0
 for ext in ['elf','bin','map']:assert (folder/('zephyr.'+ext)).exists()
 result[name]={'rom_sections_bytes':rom,'load_image_bytes':(folder/'zephyr.bin').stat().st_size,'ram_sections_bytes':ram,'ram_span_bytes':span,'ram_remaining_bytes':4194304-span,'static_pools':pools,'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'sections':sections}
resources=[]
for line in e['resources']:resources.append({key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',line)})
assert resources and min(p['stack_unused'] for p in resources)>0 and max(p['errors'] for p in resources)==0
assert resources[-1]['heap_used']<max(p['heap_used'] for p in resources)
result.update(status='PASS',runtime_samples=resources,main_stack_reserved=16384,main_stack_high_water_bytes=16384-min(p['stack_unused'] for p in resources),newlib_heap_peak_sampled=max(p['heap_peak_sampled'] for p in resources),newlib_heap_arena_peak_bytes=max(p['heap_arena_peak'] for p in resources),heap_peak_scope='Newlib official __malloc_max_total_mem exact peak of arena; live allocated bytes from mallinfo samples after initialization, every main-loop iteration, commands and finalization; not an allocation-hook exact peak',zephyr_heap_pool_reserved=131072,xrce_mtu=512,xrce_reliable_input_history=4,xrce_reliable_output_history=4,uart_rx_ring_bytes=2048,agent_rss=e['agent_rss'],external_logs=e['external_logs'])
record('memory',result);print('STAGE6_MEMORY_PASS',result['acquisition']['ram_span_bytes'],result['main_stack_high_water_bytes'])
