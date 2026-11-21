#ifndef VEL_BLOCK_DEVICE_H
#define VEL_BLOCK_DEVICE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef enum { BD_OK, BD_INVALID, BD_CLOSED, BD_RANGE, BD_READ_ONLY, BD_IO, BD_SHORT_IO, BD_GEOMETRY, BD_EXISTS, BD_UNSAFE, BD_BUSY } bd_status;
typedef struct { uint64_t sector_count; uint32_t sector_size; } bd_geometry;
typedef struct { bool open; bool read_only; } bd_media_status;
typedef struct { uint64_t bytes_completed; uint32_t blocks_completed; } bd_transfer;
typedef struct {
    bd_status (*open)(void *, const void *);
    bd_status (*close)(void *);
    bd_status (*read)(void *, uint64_t, uint32_t, void *, size_t, bd_transfer *);
    bd_status (*write)(void *, uint64_t, uint32_t, const void *, size_t, bd_transfer *);
    bd_status (*sync)(void *);
    bd_status (*geometry)(void *, bd_geometry *);
    bd_status (*status)(void *, bd_media_status *);
} bd_ops;
typedef struct { const bd_ops *ops; void *context; } bd_device;
bd_status bd_open(bd_device *, const void *);
bd_status bd_close(bd_device *);
bd_status bd_read_blocks(bd_device *, uint64_t, uint32_t, void *, size_t, bd_transfer *);
bd_status bd_write_blocks(bd_device *, uint64_t, uint32_t, const void *, size_t, bd_transfer *);
bd_status bd_sync(bd_device *);
bd_status bd_get_geometry(bd_device *, bd_geometry *);
bd_status bd_get_status(bd_device *, bd_media_status *);
const char *bd_status_name(bd_status);
#endif
