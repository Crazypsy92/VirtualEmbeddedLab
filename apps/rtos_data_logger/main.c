#include "vel_runtime.h"
#include "uart.h"
#include "queue.h"
#include "semphr.h"
#include "ff.h"
#include "vel_diskio.h"
#include "ram_storage.h"
#include "ff_mutex.h"
#include <string.h>
#ifndef SCENARIO
#define SCENARIO 0
#endif
#define RECORDS 128U
#define CAPACITY 8U
typedef struct { uint32_t sensor,sequence,tick,value,check; } record;
_Static_assert(sizeof(record)==20,"wire record size");
static record model[2][RECORDS];
static unsigned char scratch[1024];
static FATFS fs;
static ram_storage storage;
static bd_device device;
static QueueHandle_t samples;
static SemaphoreHandle_t held,released;
TaskHandle_t g_logger_handle,g_reader_handle,g_sensor_handles[2],g_monitor_handle;
volatile uint32_t g_produced[2],g_written,g_verified,g_model_hash=2166136261U,g_read_hash=2166136261U,g_file_bytes;
volatile uint32_t g_stop,g_logger_done,g_reader_done,g_sensor_mask,g_error_code,g_error_location,g_partial_blocks,g_queue_timeout,g_qblocks[2],g_reader_ops;
volatile uint32_t g_fault_bytes,g_fault_blocks,g_fault_reads,g_fault_writes,g_fault_hits;
static uint32_t checksum(const record *r) { return r->sensor ^ (r->sequence*0x9E3779B9U) ^ r->tick ^ r->value ^ 0xC003A55AU; }
static uint32_t feed(uint32_t h,const void *b,size_t size) { const unsigned char *s=b; for (size_t i=0;i<size;++i) { h^=s[i]; h*=16777619U; } return h; }
static void stop_error(uint32_t code,uint32_t location)
{
    taskENTER_CRITICAL();
    if (!g_error_code) {
        g_error_code=code; g_error_location=location;
        if (code==FR_DISK_ERR) { g_fault_bytes=(uint32_t)storage.last.bytes_completed; g_fault_blocks=storage.last.blocks_completed; g_fault_reads=storage.read_calls; g_fault_writes=storage.write_calls; g_fault_hits=storage.hits; }
    } g_stop=1;
    taskEXIT_CRITICAL();
}
static bool logger_fault_owner(void) { return xTaskGetCurrentTaskHandle()==g_logger_handle; }
static void io_yield(void) { vTaskDelay(1); }
static void sensor_task(void *arg)
{
    uint32_t id=(uint32_t)(uintptr_t)arg; REQUIRE(ulTaskNotifyTake(pdTRUE,1000)==1);
    for (uint32_t i=0;i<RECORDS && !g_stop;++i) {
        record *r=&model[id][i]; r->sensor=id; r->sequence=i; r->tick=xTaskGetTickCount(); r->value=id*100000U+i*37U; r->check=checksum(r);
        if (xQueueSend(samples,r,0)!=pdTRUE) {
            ++g_qblocks[id];
            if (xQueueSend(samples,r,500)!=pdTRUE) { if (!g_stop) { stop_error(102,6); } break; }
        }
        ++g_produced[id]; vTaskDelay(1);
    }
    taskENTER_CRITICAL(); g_sensor_mask|=1U<<id; taskEXIT_CRITICAL(); vTaskSuspend(NULL);
}
__attribute__((noinline)) void logger_write_marker(void) { __asm volatile("nop" ::: "memory"); }
static void logger_task(void *arg)
{
    (void)arg; REQUIRE(ulTaskNotifyTake(pdTRUE,1000)==1);
    if (g_stop) { g_logger_done=1; vTaskSuspend(NULL); }
    FIL file; FRESULT result=f_open(&file,"0:/LOG.BIN",FA_CREATE_NEW|FA_WRITE); REQUIRE(result==FR_OK); REQUIRE(f_sync(&file)==FR_OK);
    if (SCENARIO==1 || SCENARIO==2) { ram_fault_filter=logger_fault_owner; ram_fault(&storage,0,1,SCENARIO==2 ? 1U : 0U); }
    if (SCENARIO==2) {
        memset(scratch,0x6B,sizeof scratch); UINT n=0; result=f_write(&file,scratch,sizeof scratch,&n);
        REQUIRE(result==FR_DISK_ERR && storage.last.blocks_completed==1 && storage.last.bytes_completed==512U && storage.hits==1);
        g_partial_blocks=storage.last.blocks_completed; stop_error(result,3);
    }
    uint32_t next[2]={0,0};
    while (!g_stop && g_written<256U) {
        record r; if (xQueueReceive(samples,&r,500)!=pdTRUE) { stop_error(103,6); break; }
        REQUIRE(r.sensor<2U && r.sequence<128U && r.sequence==next[r.sensor] && r.check==checksum(&r));
        REQUIRE(memcmp(&r,&model[r.sensor][r.sequence],sizeof r)==0);
        logger_write_marker(); UINT n=0; result=f_write(&file,&r,sizeof r,&n);
        if (result!=FR_OK || n!=sizeof r) { stop_error(result!=FR_OK ? (uint32_t)result : 104U,1); break; }
        ++next[r.sensor]; ++g_written; g_model_hash=feed(g_model_hash,&r,sizeof r);
        if (g_written%16U==0U) { result=f_sync(&file); if (result!=FR_OK) { stop_error(result,2); break; } }
    }
    if (!g_stop) { REQUIRE(f_sync(&file)==FR_OK && f_close(&file)==FR_OK); }
    else { vel_stat("close_after_error",f_close(&file)); }
    if (!g_stop) {
        REQUIRE(next[0]==128U && next[1]==128U); REQUIRE(f_open(&file,"0:/LOG.BIN",FA_READ)==FR_OK); g_file_bytes=f_size(&file); REQUIRE(g_file_bytes==256U*sizeof(record));
        if (SCENARIO==3) { ram_fault_filter=logger_fault_owner; ram_fault(&storage,1,0,0); }
        uint32_t verify_next[2]={0,0},last_tick[2]={0,0};
        for (uint32_t i=0;i<256U;++i) {
            record r; UINT n=0; result=f_read(&file,&r,sizeof r,&n);
            if (result!=FR_OK || n!=sizeof r) { stop_error(result!=FR_OK ? (uint32_t)result : 105U,4); break; }
            REQUIRE(r.sensor<2U && r.sequence==verify_next[r.sensor] && r.sequence<128U && r.tick>=last_tick[r.sensor]);
            REQUIRE(r.value==r.sensor*100000U+r.sequence*37U && r.check==checksum(&r) && memcmp(&r,&model[r.sensor][r.sequence],sizeof r)==0);
            ++verify_next[r.sensor]; last_tick[r.sensor]=r.tick; ++g_verified; g_read_hash=feed(g_read_hash,&r,sizeof r);
        }
        if (!g_stop) { REQUIRE(g_verified==256U && g_read_hash==g_model_hash && verify_next[0]==128 && verify_next[1]==128); }
        result=f_close(&file); REQUIRE(result==FR_OK || g_stop);
    }
    g_logger_done=1; vTaskSuspend(NULL);
}
static void reader_task(void *arg)
{
    (void)arg; REQUIRE(ff_mutex_take(0)); REQUIRE(xSemaphoreGive(held)==pdTRUE); vTaskDelay(40); ff_mutex_give(0); REQUIRE(xSemaphoreGive(released)==pdTRUE);
    REQUIRE(ulTaskNotifyTake(pdTRUE,1000)==1);
    while (!g_stop && !g_logger_done) {
        FIL f; unsigned char data[512]; memset(data,(int)(g_reader_ops&255U),sizeof data);
        FRESULT r=f_open(&f,"0:/SIDE.BIN",FA_WRITE);
        if (r!=FR_OK) { stop_error(r,9); break; }
        r=f_lseek(&f,0); UINT n=0;
        if (r==FR_OK) { r=f_write(&f,data,sizeof data,&n); if (r==FR_OK && n!=sizeof data) { r=FR_DISK_ERR; } }
        if (r==FR_OK) { r=f_sync(&f); }
        FRESULT closed=f_close(&f); if (r==FR_OK) { r=closed; }
        if (r!=FR_OK) { stop_error(r,9); break; }
        FILINFO info; r=f_stat("0:/SIDE.BIN",&info);
        if (r!=FR_OK) { stop_error(r,9); break; }
        REQUIRE(info.fsize==512); ++g_reader_ops; vTaskDelay(2);
    }
    g_reader_done=1; vTaskSuspend(NULL);
}
static void finish_stats(void)
{
    vel_stat("sizeof_fs",sizeof(FATFS)); vel_stat("sizeof_file",sizeof(FIL));
    vel_stat("scenario",SCENARIO); vel_stat("produced_a",g_produced[0]); vel_stat("produced_b",g_produced[1]); vel_stat("written",g_written); vel_stat("verified",g_verified); vel_stat("file_bytes",g_file_bytes);
    vel_stat("model_hash",g_model_hash); vel_stat("read_hash",g_read_hash); vel_stat("fs_takes",g_fs_takes); vel_stat("fs_gives",g_fs_gives); vel_stat("fs_timeouts",g_fs_timeouts); vel_stat("fs_contention",g_fs_contention);
    vel_stat("reader_ops",g_reader_ops); vel_stat("queue_timeout",g_queue_timeout); vel_stat("queue_blocks",g_qblocks[0]+g_qblocks[1]); vel_stat("partial_blocks",g_partial_blocks);
    vel_stat("fault_bytes",g_fault_bytes); vel_stat("fault_blocks",g_fault_blocks); vel_stat("fault_reads",g_fault_reads); vel_stat("fault_writes",g_fault_writes); vel_stat("fault_hits",g_fault_hits);
    vel_stat("asserts",g_asserts); vel_stat("hardfaults",g_hardfaults); vel_stat("stack_faults",g_stack_faults);
    vel_stat("error_code",g_error_code); vel_stat("error_location",g_error_location); vel_stat("stopped",g_stop); vel_stat("malloc_expected",g_malloc_failures);
    vel_stat("ticks",g_tick_hook); vel_stat("switches",g_switches); vel_stat("heap_free",(uint32_t)xPortGetFreeHeapSize()); vel_stat("heap_min",(uint32_t)xPortGetMinimumEverFreeHeapSize());
    vel_stat("stack_logger",(uint32_t)uxTaskGetStackHighWaterMark(g_logger_handle)); vel_stat("stack_reader",(uint32_t)uxTaskGetStackHighWaterMark(g_reader_handle)); vel_stat("stack_monitor",(uint32_t)uxTaskGetStackHighWaterMark(g_monitor_handle));
    vel_stat("stack_sensor_a",(uint32_t)uxTaskGetStackHighWaterMark(g_sensor_handles[0])); vel_stat("stack_sensor_b",(uint32_t)uxTaskGetStackHighWaterMark(g_sensor_handles[1]));
    vel_stat("stack_idle",(uint32_t)uxTaskGetStackHighWaterMark(xTaskGetIdleTaskHandle()));
    g_result=g_error_code ? 1U : 0U; vel_stat("result",g_result); vel_complete(); vel_finish(g_result ? 42U : 0U);
}
static void monitor_task(void *arg)
{
    (void)arg; ram_storage_init(&storage,&device); ram_config c={true,false}; REQUIRE(bd_open(&device,&c)==BD_OK); vel_disk_bind(&device);
    unsigned char work[4096]; MKFS_PARM options={.fmt=FM_FAT|FM_SFD,.n_fat=2,.align=1,.n_root=512,.au_size=1024}; REQUIRE(f_mkfs("0:",&options,work,sizeof work)==FR_OK); REQUIRE(f_mount(&fs,"0:",1)==FR_OK);
    FIL side; REQUIRE(f_open(&side,"0:/SIDE.BIN",FA_CREATE_NEW|FA_WRITE)==FR_OK && f_close(&side)==FR_OK);
    record dummy={0};
    for (uint32_t i=0;i<CAPACITY;++i) { REQUIRE(xQueueSend(samples,&dummy,0)==pdTRUE); }
    TickType_t start=xTaskGetTickCount(); REQUIRE(xQueueSend(samples,&dummy,2)==errQUEUE_FULL && xTaskGetTickCount()-start>=2U); ++g_queue_timeout;
    for (uint32_t i=0;i<CAPACITY;++i) { REQUIRE(xQueueReceive(samples,&dummy,0)==pdTRUE); }
    REQUIRE(xTaskCreate(logger_task,"Logger",1536,NULL,2,&g_logger_handle)==pdPASS);
    REQUIRE(xTaskCreate(reader_task,"Reader",1024,NULL,2,&g_reader_handle)==pdPASS);
    REQUIRE(xTaskCreate(sensor_task,"SensorA",512,(void *)(uintptr_t)0,1,&g_sensor_handles[0])==pdPASS);
    REQUIRE(xTaskCreate(sensor_task,"SensorB",512,(void *)(uintptr_t)1,1,&g_sensor_handles[1])==pdPASS);
    REQUIRE(xSemaphoreTake(held,100)==pdTRUE); FILINFO info; start=xTaskGetTickCount(); FRESULT r=f_stat("0:/SIDE.BIN",&info); REQUIRE(r==FR_TIMEOUT && xTaskGetTickCount()-start>=20U);
    REQUIRE(xSemaphoreTake(released,100)==pdTRUE);
    if (SCENARIO==5) { stop_error(r,7); }
    if (SCENARIO==6) { stop_error(101,8); }
    if (SCENARIO==4) { g_expect_malloc=1; REQUIRE(pvPortMalloc(configTOTAL_HEAP_SIZE)==NULL); g_expect_malloc=0; REQUIRE(g_malloc_failures==1); stop_error(100,5); }
    ram_io_hook=io_yield;
    xTaskNotifyGive(g_logger_handle); xTaskNotifyGive(g_reader_handle); xTaskNotifyGive(g_sensor_handles[0]); xTaskNotifyGive(g_sensor_handles[1]);
    start=xTaskGetTickCount();
    while (!g_logger_done || !g_reader_done || g_sensor_mask!=3U) { REQUIRE(xTaskGetTickCount()-start<3000U); vTaskDelay(5); }
    ram_io_hook=NULL; ram_fault_filter=NULL; REQUIRE(g_fs_takes==g_fs_gives && g_fs_owner==NULL);
    if (SCENARIO==0) { REQUIRE(!g_stop && g_written==256 && g_verified==256 && g_reader_ops>0 && g_fs_contention>1 && g_fs_timeouts==1); }
    if (SCENARIO==1) { REQUIRE(g_error_code==FR_DISK_ERR && g_written<256 && storage.hits==1); }
    if (SCENARIO==2) { REQUIRE(g_error_code==FR_DISK_ERR && g_partial_blocks==1 && g_written==0); }
    if (SCENARIO==3) { REQUIRE(g_error_code==FR_DISK_ERR && g_written==256 && g_verified==0 && storage.hits==1); }
    REQUIRE(!g_asserts && !g_stack_faults && !g_hardfaults);
    REQUIRE(f_mount(NULL,"0:",0)==FR_OK); vel_disk_bind(NULL); REQUIRE(bd_close(&device)==BD_OK);
    finish_stats();
}
int main(void)
{
    REQUIRE(uart_init()); samples=xQueueCreate(CAPACITY,sizeof(record)); held=xSemaphoreCreateBinary(); released=xSemaphoreCreateBinary(); REQUIRE(samples && held && released);
    uart_puts("[BOOT] RTOS FatFs Logger\n"); REQUIRE(xTaskCreate(monitor_task,"Monitor",3072,NULL,3,&g_monitor_handle)==pdPASS); vTaskStartScheduler(); REQUIRE(0); return 1;
}
