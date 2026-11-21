#ifndef VEL_RAM_STORAGE_H
#define VEL_RAM_STORAGE_H
#include "block_device/block_device.h"
#define RAM_SECTORS 4096U
#define RAM_BYTES (RAM_SECTORS*512U)
typedef struct { bool clear,read_only; } ram_config;
typedef struct { bool opened,read_only; uint32_t read_calls,write_calls,read_on,write_on,partial,hits; bd_transfer last; } ram_storage;
extern void (*ram_io_hook)(void);
extern bool (*ram_fault_filter)(void);
extern unsigned char ram_bytes[RAM_BYTES];
void ram_storage_init(ram_storage *,bd_device *);
void ram_fault(ram_storage *,uint32_t,uint32_t,uint32_t);
#endif
