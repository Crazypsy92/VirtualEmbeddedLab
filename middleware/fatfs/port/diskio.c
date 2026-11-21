#include "ff.h"
#include "diskio.h"
#include "vel_diskio.h"
#include <limits.h>
static bd_device *device;
void vel_disk_bind(bd_device *d) { device=d; }
static DRESULT map(bd_status s)
{
    switch(s) {
    case BD_OK: return RES_OK;
    case BD_INVALID: case BD_RANGE: return RES_PARERR;
    case BD_CLOSED: return RES_NOTRDY;
    case BD_READ_ONLY: return RES_WRPRT;
    default: return RES_ERROR;
    }
}
DSTATUS disk_status(BYTE drive)
{
    bd_media_status m; bd_geometry g;
    if (drive!=0 || bd_get_status(device,&m)!=BD_OK || !m.open || bd_get_geometry(device,&g)!=BD_OK) { return STA_NOINIT; }
    return m.read_only ? STA_PROTECT : 0;
}
DSTATUS disk_initialize(BYTE drive) { return disk_status(drive); }
DRESULT disk_read(BYTE drive,BYTE *buffer,LBA_t lba,UINT count)
{
    if (drive!=0 || buffer==NULL || count==0 || (uint64_t)count*512U>SIZE_MAX) { return RES_PARERR; }
    if (device==NULL) { return RES_NOTRDY; }
    bd_transfer t; return map(bd_read_blocks(device,lba,count,buffer,(size_t)count*512U,&t));
}
DRESULT disk_write(BYTE drive,const BYTE *buffer,LBA_t lba,UINT count)
{
    if (drive!=0 || buffer==NULL || count==0 || (uint64_t)count*512U>SIZE_MAX) { return RES_PARERR; }
    if (device==NULL) { return RES_NOTRDY; }
    bd_transfer t; return map(bd_write_blocks(device,lba,count,buffer,(size_t)count*512U,&t));
}
DRESULT disk_ioctl(BYTE drive,BYTE cmd,void *buffer)
{
    if (drive!=0) { return RES_PARERR; }
    if (device==NULL) { return RES_NOTRDY; }
    if (cmd==CTRL_SYNC) { return map(bd_sync(device)); }
    if (buffer==NULL) { return RES_PARERR; }
    bd_geometry g; bd_status s=bd_get_geometry(device,&g); if (s!=BD_OK) { return map(s); }
    switch(cmd) {
    case GET_SECTOR_COUNT:
        if (g.sector_count>UINT32_MAX) { return RES_PARERR; } *(LBA_t *)buffer=(LBA_t)g.sector_count; return RES_OK;
    case GET_SECTOR_SIZE: *(WORD *)buffer=(WORD)g.sector_size; return RES_OK;
    case GET_BLOCK_SIZE: *(DWORD *)buffer=1; return RES_OK;
    default: return RES_PARERR;
    }
}
