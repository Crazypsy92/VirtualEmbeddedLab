#ifndef VEL_HOST_STORAGE_H
#define VEL_HOST_STORAGE_H
#include "block_device/block_device.h"
#define HOST_SD_SECTORS UINT64_C(65536)
#define HOST_SD_SECTOR_SIZE 512U
typedef struct { const char *root; const char *name; uint64_t sectors; bool create_new; bool read_only; } host_storage_config;
/* One-shot 1-based operation numbers; zero disables. Partial blocks are committed before IO error. */
typedef struct { uint64_t read_on, write_on, sync_on; uint32_t partial_blocks; bool short_io; } host_fault_plan;
typedef struct {
    int fd;
    bool opened, read_only;
    uint64_t sectors, read_calls, write_calls, sync_calls, fault_hits;
    host_fault_plan fault;
} host_storage;
void host_storage_init(host_storage *, bd_device *);
void host_storage_fault_reset(host_storage *, const host_fault_plan *);
#endif
