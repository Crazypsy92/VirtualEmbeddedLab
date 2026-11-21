ENTRY(Reset_Handler)
/* AN385 ZBT SSRAM, not STM32 flash. QEMU loads the ELF LMA into CODE. */
MEMORY {
  CODE (rx) : ORIGIN = 0x00000000, LENGTH = 4M
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 4M
}
_stack_top = ORIGIN(RAM) + LENGTH(RAM);
_stack_limit = _stack_top - 16K;
SECTIONS {
  .isr_vector : ALIGN(256) { KEEP(*(.isr_vector)) } > CODE
  .text : ALIGN(4) { *(.text*) *(.rodata*) . = ALIGN(4); } > CODE
  .ARM.exidx : { *(.ARM.exidx*) } > CODE
  .data : ALIGN(4) { _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > CODE
  _sidata = LOADADDR(.data);
  .bss (NOLOAD) : ALIGN(8) { _sbss = .; *(.bss*) *(COMMON) . = ALIGN(8); _ebss = .; } > RAM
  /DISCARD/ : { *(.comment*) *(.note*) }
}
ASSERT(ADDR(.isr_vector) == 0, "Vectors must start at zero")
ASSERT(SIZEOF(.isr_vector) == 192, "48 vectors required")
ASSERT(_ebss <= _stack_limit, "RAM overlaps reserved MSP stack")
ASSERT((_stack_top & 7) == 0, "Stack alignment")
