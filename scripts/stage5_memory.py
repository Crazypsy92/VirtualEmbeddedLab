#!/usr/bin/env python3
from stage5_support import *
from stage5_uart_test import ELF
import hashlib
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='memory-',dir=WS/'runs'));r=run_command(['arm-none-eabi-size','-A',ELF],os.environ.copy());assert r.returncode==0
(d/'size.log').write_text(r.stdout);sections={}
for line in r.stdout.splitlines():
    f=line.split()
    if len(f)==3 and f[1].isdigit() and f[2].isdigit():sections[f[0]]={'size':int(f[1]),'address':int(f[2])}
rom=ram=0;intervals=[]
for name,p in sections.items():
    a,n=p['address'],p['size']
    if 0x20000000<=a<0x20400000:
        ram+=n;assert a+n<=0x20400000
        if n:intervals.append((a,a+n))
    elif a<0x400000 and not name.startswith(('.debug','.ARM.attributes','.comment')):rom+=n
intervals.sort();assert all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:]));assert rom>1000 and ram>3072
folder=ELF.parent;cfg=(folder/'.config').read_text();dt=(folder/'zephyr.dts').read_text()
assert 'CONFIG_HEAP_MEM_POOL_SIZE=0' in cfg and 'CONFIG_MAIN_STACK_SIZE=3072' in cfg
for ext in ['elf','bin','map']:assert (folder/('zephyr.'+ext)).exists()
(d/'config.txt').write_text(cfg);(d/'devicetree.dts').write_text(dt)
ram_span=intervals[-1][1]-0x20000000
result={'status':'PASS','load_image_bytes':(folder/'zephyr.bin').stat().st_size,'ram_span_bytes':ram_span,'ram_alignment_padding_bytes':ram_span-ram,'rom_sections_bytes':rom,'ram_sections_bytes':ram,'ram_capacity':4194304,'ram_remaining_bytes':4194304-ram_span,'main_stack_reserved_bytes':3072,'heap_pool_bytes':0,'wire_static_buffers_bytes':82*3,'max_payload_bytes':64,'max_raw_frame_bytes':78,'encoded_allocation_bytes':82,'elf_sha256':hashlib.sha256(ELF.read_bytes()).hexdigest(),'sections':sections,'external_logs':str(d),'stack_high_water':'NOT MEASURED; reserved stacks included in static RAM'}
record('memory',result);print('STAGE5_MEMORY_PASS',rom,ram)
