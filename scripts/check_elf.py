#!/usr/bin/env python3
"""Check ELF metadata using binutils; inspect binary vector values."""
import pathlib
import re
import struct
import subprocess
from run_qemu import ROOT
elf = ROOT/'build/arm/cortex_m3_demo.elf'
def run(*cmd):
    r = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=True)
    print('$ ' + ' '.join(cmd) + '\n' + r.stdout)
    return r.stdout
info = run('arm-none-eabi-readelf', '-h', '-S', '-l', str(elf))
listing = run('arm-none-eabi-nm', '-n', str(elf))
symbols = {}
for line in listing.splitlines():
    fields = line.split()
    if len(fields) == 3: symbols[fields[2]] = int(fields[0],16)
blob = (elf.with_suffix('.bin')).read_bytes()
vectors = struct.unpack('<48I',blob[:192])
assert vectors[0] == symbols['_stack_top'] == 0x20400000
for slot, symbol in [(1,'Reset_Handler'),(2,'Default_Handler'),(3,'HardFault_Handler'),(11,'SVC_Handler'),(14,'PendSV_Handler'),(15,'SysTick_Handler')]:
    assert vectors[slot] == symbols[symbol] | 1, (slot,symbol)
assert all(vectors[i] == 0 for i in [7,8,9,10,13])
assert all(vectors[i] == symbols['Default_Handler'] | 1 for i in range(16,48))
assert symbols['vector_table'] == 0
assert int(re.search(r'Entry point address:\s+(0x[0-9a-fA-F]+)',info)[1],16) == vectors[1]
assert 0x20000000 == symbols['_sdata'] < symbols['_edata'] <= symbols['_sbss'] < symbols['_ebss'] <= symbols['_stack_limit'] < symbols['_stack_top']
assert symbols['_sidata'] < 0x400000
assert re.search(r'\.bss\s+NOBITS',info)
for offset,symbol in [(0,'_sidata')]:
    data = struct.unpack_from('<4I',blob,symbols[symbol]+offset)
    assert data == (0x12345678,0xABCDEF01,0x55AA55AA,0xC003C003)
assert elf.with_suffix('.map').stat().st_size > 0
print('ELF_LAYOUT_PASS: vectors, Thumb reset entry, data LMA, BSS, RAM/MSP bounds, BIN and MAP')
