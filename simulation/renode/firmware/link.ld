ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 20K }
SECTIONS {
.vectors : { KEEP(*(.vectors)) } > FLASH
.text : { *(.text*) *(.rodata*) } > FLASH
.data : { *(.data*) } > RAM AT> FLASH
.bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
_stack = ORIGIN(RAM) + LENGTH(RAM);
}
