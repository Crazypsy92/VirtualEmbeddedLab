#!/usr/bin/env python3
import pathlib,subprocess,json,re,hashlib,os
ROOT=pathlib.Path(__file__).resolve().parents[1]; results={}
for elf in sorted((ROOT/'build/freertos').glob('*.elf')):
    nm=subprocess.check_output(['arm-none-eabi-nm','-n','-S',str(elf)],text=True)
    symbols={}
    for line in nm.splitlines():
        f=line.split()
        if len(f)>=3: symbols[f[-1]]=int(f[0],16)
    size=subprocess.check_output(['arm-none-eabi-size','-A',str(elf)],text=True)
    sections={}
    for line in size.splitlines():
        f=line.split()
        if len(f)==3 and f[0].startswith('.'): sections[f[0]]=int(f[1])
    assert symbols['vector_table']==0 and symbols['_ebss']<=symbols['_stack_limit']==0x203fc000 and symbols['_stack_top']==0x20400000
    assert symbols['_sdata']==0x20200000 and symbols['_ramdisk_start']==0x20000000
    disk=sections.get('.ramdisk',0)
    assert disk in [0,2097152]
    if disk: assert symbols['_ramdisk_end']==0x20200000
    assert not any(re.search(r'\b'+name+r'$',nm,re.M) for name in ['host_storage_init','pread','pwrite','ftruncate','fsync'])
    for suffix in ['.bin','.map']: assert elf.with_suffix(suffix).is_file()
    results[elf.stem]={'code_ro_bytes':sum(sections.get(n,0) for n in ['.text','.isr_vector','.ARM.exidx']),'data_bytes':sections.get('.data',0),'bss_bytes':sections.get('.bss',0),'ram_disk_bytes':disk,'msp_reserve_bytes':16384,'general_ram_free_below_msp':0x203fc000-symbols['_ebss'],'heap_config_bytes':98304,'sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'sections':sections}
    (pathlib.Path(os.environ.get('VEL_STAGE3_EVIDENCE',str(ROOT/'evidence/stage3')))/('memory_'+elf.stem+'.log')).write_text('$ arm-none-eabi-size -A '+str(elf)+'\n'+size+'\n$ arm-none-eabi-nm -n -S '+str(elf)+'\n'+nm)
(pathlib.Path(os.environ.get('VEL_STAGE3_EVIDENCE',str(ROOT/'evidence/stage3')))/'memory.json').write_text(json.dumps(results,indent=2)+'\n')
print('ARM_MEMORY_PASS targets='+str(len(results)))
