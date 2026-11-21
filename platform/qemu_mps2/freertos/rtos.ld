ENTRY(Reset_Handler)
/* AN385: actual SSRAM1 and SSRAM2/3. Reserve separate 2 MiB for future RAM disk. */
MEMORY {
 CODE(rx) : ORIGIN = 0x00000000, LENGTH = 4M
 DISK(rw) : ORIGIN = 0x20000000, LENGTH = 2M
 RAM(rwx) : ORIGIN = 0x20200000, LENGTH = 2M
}
_stack_top = ORIGIN(RAM)+LENGTH(RAM);
_stack_limit = _stack_top-16K;
SECTIONS {
 .isr_vector : ALIGN(256) { KEEP(*(.isr_vector)) } > CODE
 .text : ALIGN(4) { *(.text*) *(.rodata*) .  =  ALIGN(4); } > CODE
 .ARM.exidx : { *(.ARM.exidx*) } > CODE
 .data : ALIGN(4) { _sdata = .; *(.data*) .  =  ALIGN(4); _edata = .; } > RAM AT > CODE
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : ALIGN(8) { _sbss = .; *(.bss*) *(COMMON) .  =  ALIGN(8); _ebss = .; } > RAM
 .ramdisk (NOLOAD) : ALIGN(512) { _ramdisk_start = .; *(.ramdisk*) _ramdisk_end = .; } > DISK
 /DISCARD/ : { *(.comment*) *(.note*) }
}
ASSERT(_ebss <= _stack_limit,"MSP overlap")
ASSERT(SIZEOF(.isr_vector)==192,"Vector count")
ASSERT(SIZEOF(.ramdisk)<=LENGTH(DISK),"Disk overflow")
