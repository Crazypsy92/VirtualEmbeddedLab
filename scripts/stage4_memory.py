#!/usr/bin/env python3
from stage4_support import *
import json,re,hashlib
result={}
for name in ['hello','sync','kernel','sensor','sensor_off','acquisition']:
    folder=ROOT/'build/zephyr'/name/'zephyr'; elf=folder/'zephyr.elf'
    rc,text=call('resources/'+name,['arm-none-eabi-size','-A',elf]); assert rc==0
    sections={}
    for line in text.splitlines():
        f=line.split()
        if len(f)==3 and f[1].isdigit() and f[2].isdigit(): sections[f[0]]={'size':int(f[1]),'address':int(f[2])}
    ram=0; rom=0; ram_intervals=[]
    for sec,v in sections.items():
        if 0x20000000<=v['address']<0x20400000:
            assert v['address']+v['size']<=0x20400000; ram+=v['size']
            if v['size']: ram_intervals.append((v['address'],v['address']+v['size'],sec))
        elif v['address']<0x400000 and not sec.startswith(('.debug','.ARM.attributes','.comment')): rom+=v['size']
    assert rom>1000 and ram>1024, 'suspicious resource totals'
    ram_intervals.sort()
    assert all(a[1]<=b[0] for a,b in zip(ram_intervals,ram_intervals[1:])), 'RAM sections overlap'
    cfg=(folder/'.config').read_text(); assert 'CONFIG_SOC_AN385=y' in cfg or 'CONFIG_BOARD_MPS2_AN385=y' in cfg
    result[name]={'rom_sections_bytes':rom,'ram_sections_bytes':ram,'ram_remaining_bytes':4194304-ram,'heap_pool_bytes':0 if 'CONFIG_HEAP_MEM_POOL_SIZE=0' in cfg else 'see config','elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'sections':sections}
    for ext in ['elf','bin','map']: assert (folder/('zephyr.'+ext)).exists()
    (OUT/'resources'/('config_'+name+'.txt')).write_text(cfg)
    (OUT/'resources'/('devicetree_'+name+'.dts')).write_bytes((folder/'zephyr.dts').read_bytes())
(OUT/'memory.json').write_text(json.dumps(result,indent=2)+'\n'); print('ZEPHYR_MEMORY_VERIFIED')
