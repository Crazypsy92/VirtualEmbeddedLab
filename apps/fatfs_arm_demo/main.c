#include "vel_runtime.h"
#include "uart.h"
#include "ff.h"
#include "vel_diskio.h"
#include "ram_storage.h"
#include <string.h>
static FATFS fs;
static ram_storage storage;
static bd_device device;
static unsigned char data[8193],back[8194];
volatile uint32_t g_fs_bytes,g_fs_hash,g_fs_remount,g_ram_faults;
static TaskHandle_t handle;
#define FOK(x) REQUIRE((x)==FR_OK)
static void fs_task(void *arg)
{
    (void)arg; vTaskDelay(5);
    ram_storage_init(&storage,&device); ram_config config={true,false}; REQUIRE(bd_open(&device,&config)==BD_OK); vel_disk_bind(&device);
    bd_geometry geo; REQUIRE(bd_get_geometry(&device,&geo)==BD_OK && geo.sector_count==4096 && geo.sector_size==512);
    bd_transfer transfer; REQUIRE(bd_read_blocks(&device,UINT64_MAX,1,back,512,&transfer)==BD_RANGE);
    REQUIRE(bd_read_blocks(&device,0,0,back,512,&transfer)==BD_INVALID);
    unsigned char work[4096]; MKFS_PARM options={.fmt=FM_FAT|FM_SFD,.n_fat=2,.align=1,.n_root=512,.au_size=1024};
    FOK(f_mkfs("0:",&options,work,sizeof work)); FOK(f_mount(&fs,"0:",1)); REQUIRE(fs.fs_type==FS_FAT12 && fs.csize==2);
    vel_stat("fat_type",fs.fs_type); vel_stat("cluster_bytes",fs.csize*512U); vel_stat("fat_sectors",fs.fsize); vel_stat("data_lba",fs.database);
    DWORD before,after; FATFS *ptr; FOK(f_getfree("0:",&before,&ptr));
    for (uint32_t i=0;i<sizeof data;++i) { data[i]=(unsigned char)(((i*31U+(i>>3))^0x5AU)&255U); }
    FIL file; UINT n; FOK(f_open(&file,"0:/ARM.BIN",FA_CREATE_NEW|FA_WRITE)); FOK(f_write(&file,data,sizeof data,&n)); REQUIRE(n==sizeof data); FOK(f_sync(&file)); FOK(f_close(&file));
    FOK(f_getfree("0:",&after,&ptr)); REQUIRE(before-after==9U);
    FOK(f_mount(NULL,"0:",0)); FOK(f_mount(&fs,"0:",1)); ++g_fs_remount;
    FOK(f_open(&file,"0:/ARM.BIN",FA_READ)); REQUIRE(f_size(&file)==sizeof data);
    FOK(f_lseek(&file,511)); FOK(f_read(&file,back,1003,&n)); REQUIRE(n==1003 && memcmp(back,data+511,1003)==0);
    FOK(f_lseek(&file,0)); FOK(f_read(&file,back,sizeof back,&n)); REQUIRE(n==sizeof data && memcmp(data,back,n)==0);
    g_fs_bytes=n; g_fs_hash=2166136261U; for (UINT i=0;i<n;++i) { g_fs_hash^=back[i]; g_fs_hash*=16777619U; } FOK(f_close(&file));
    FOK(f_unlink("0:/ARM.BIN")); FOK(f_getfree("0:",&after,&ptr)); REQUIRE(before==after);
    memset(back,0,1024); REQUIRE(bd_write_blocks(&device,4094,2,back,1024,&transfer)==BD_OK);
    ram_fault(&storage,0,1,1); REQUIRE(bd_write_blocks(&device,4094,2,data,1024,&transfer)==BD_IO && transfer.blocks_completed==1 && storage.hits==1); ++g_ram_faults;
    ram_fault(&storage,0,0,0); REQUIRE(bd_read_blocks(&device,4094,2,back,1024,&transfer)==BD_OK); REQUIRE(memcmp(back,data,512)==0); for (UINT i=512;i<1024;++i) { REQUIRE(back[i]==0); }
    FOK(f_mount(NULL,"0:",0)); ram_fault(&storage,1,0,0); REQUIRE(f_mount(&fs,"0:",1)==FR_DISK_ERR && storage.hits==1); ++g_ram_faults;
    ram_fault(&storage,0,0,0); FOK(f_mount(&fs,"0:",1)); FOK(f_mount(NULL,"0:",0)); REQUIRE(bd_sync(&device)==BD_OK); REQUIRE(bd_close(&device)==BD_OK);
    REQUIRE(bd_read_blocks(&device,0,1,back,512,&transfer)==BD_CLOSED);
    vel_stat("sizeof_fs",sizeof(FATFS)); vel_stat("sizeof_file",sizeof(FIL));
    vel_stat("fs_bytes",g_fs_bytes); vel_stat("fs_hash",g_fs_hash); vel_stat("remount",g_fs_remount); vel_stat("ram_faults",g_ram_faults); vel_stat("space_restored",before==after);
    vel_stat("ram_bytes",RAM_BYTES); vel_stat("ticks",g_tick_hook); vel_stat("switches",g_switches); vel_stat("stack_fs",(uint32_t)uxTaskGetStackHighWaterMark(handle)); vel_stat("heap_min",(uint32_t)xPortGetMinimumEverFreeHeapSize());
    vel_stat("stack_idle",(uint32_t)uxTaskGetStackHighWaterMark(xTaskGetIdleTaskHandle()));
    g_result=0; vel_stat("result",g_result); vel_complete(); vel_finish(0);
}
int main(void)
{
    REQUIRE(uart_init()); uart_puts("[BOOT] ARM RAM FatFs\n"); REQUIRE(xTaskCreate(fs_task,"ArmFatFs",3072,NULL,2,&handle)==pdPASS); vTaskStartScheduler(); REQUIRE(0); return 1;
}
