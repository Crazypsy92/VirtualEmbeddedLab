#include "vel_test.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#pragma GCC diagnostic pop
#include <string.h>
#ifndef SCENARIO
#define SCENARIO 0
#endif
#define CAPACITY ((SCENARIO==3)?1:8)
#define LOG_CAPACITY ((SCENARIO==5)?32U:256U)
typedef struct { uint32_t sensor,sequence,uptime; int32_t value; uint32_t checksum; } record;
_Static_assert(sizeof(record)==20,"Record must be 20 bytes");
K_MSGQ_DEFINE(messages,sizeof(record),CAPACITY,4);
K_MUTEX_DEFINE(log_lock);
K_SEM_DEFINE(start,0,4);
K_SEM_DEFINE(lock_held,0,1);
K_SEM_DEFINE(lock_released,0,1);
K_SEM_DEFINE(log_done,0,1);
K_THREAD_STACK_ARRAY_DEFINE(stacks,4,1536);
struct k_thread threads[4];
record ram_log[LOG_CAPACITY];
static const struct device *const devices[]={DEVICE_DT_GET(DT_NODELABEL(sensor_a)),DEVICE_DT_GET(DT_NODELABEL(sensor_b))};
static const struct device *const bad=DEVICE_DT_GET(DT_NODELABEL(sensor_bad));
volatile uint32_t g_produced[2],g_received,g_logged,g_verified,g_peak,g_queue_waits,g_mutex_timeouts,g_reader_done,g_logger_done,g_done_mask,g_result=99;
volatile int32_t g_error;
volatile uint32_t g_location,g_hash=2166136261U,g_read_hash=2166136261U;
static uint32_t check(const record *r) { return r->sensor^(r->sequence*0x9E3779B9U)^r->uptime^(uint32_t)r->value^0xA55AC003U; }
static uint32_t hash(uint32_t h,const record *r) { const unsigned char *b=(const unsigned char *)r; for (size_t i=0;i<sizeof *r;++i) { h^=b[i]; h*=16777619U; } return h; }
static void error(int code,uint32_t location)
{
    unsigned int key=irq_lock(); if (!g_error) { g_error=code; g_location=location; } irq_unlock(key);
}
__attribute__((noinline)) void acquisition_thread_marker(uint32_t id) { (void)id; __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void acquisition_lock_marker(void) { __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void acquisition_complete(void) { __asm volatile("nop" ::: "memory"); }
static void producer(void *x,void *y,void *z)
{
    (void)y;(void)z; uint32_t id=(uint32_t)(uintptr_t)x; CHECK(k_sem_take(&start,K_MSEC(1000))==0); acquisition_thread_marker(id);
    const struct device *dev=SCENARIO==1 && id==0 ? bad : devices[id];
    if (!g_error && !device_is_ready(dev)) error(-ENODEV,1);
    for (uint32_t i=0;i<128U && !g_error;++i) {
        struct sensor_value value; int rc=sensor_sample_fetch(dev);
        if (!rc) rc=sensor_channel_get(dev,SENSOR_CHAN_AMBIENT_TEMP,&value);
        if (rc) { error(rc,2); break; }
        record r={id,i,(uint32_t)k_uptime_get(),value.val1*1000+value.val2/1000,0}; r.checksum=check(&r);
        unsigned int qkey=irq_lock();
        rc=k_msgq_put(&messages,&r,K_NO_WAIT);
        unsigned int used=k_msgq_num_used_get(&messages); if (used>g_peak) g_peak=used;
        irq_unlock(qkey);
        if (rc) { ++g_queue_waits; rc=k_msgq_put(&messages,&r,K_MSEC(10)); }
        if (rc) { error(rc,4); break; }
        ++g_produced[id];
        k_msleep(1);
    }
    unsigned int key=irq_lock(); g_done_mask|=1U<<id; irq_unlock(key);
}
static void logger(void *x,void *y,void *z)
{
    (void)x;(void)y;(void)z; CHECK(k_sem_take(&start,K_MSEC(1000))==0); acquisition_thread_marker(2);
    k_msleep(SCENARIO==4?30:3);
    uint32_t next[2]={0};
    while (!g_error && g_logged<256U) {
        record r; int rc=k_msgq_get(&messages,&r,K_MSEC(100));
        if (rc) { error(rc,7); break; } ++g_received;
        CHECK(r.sensor<2 && r.sequence<128 && r.sequence==next[r.sensor] && r.checksum==check(&r));
        int32_t expected=(r.sensor?30000:25000)+(int32_t)r.sequence*(r.sensor?40:25); CHECK(r.value==expected);
        rc=k_mutex_lock(&log_lock,K_MSEC(20)); if (rc) { error(rc,6); break; }
        if (g_logged>=LOG_CAPACITY) { CHECK(k_mutex_unlock(&log_lock)==0); error(-ENOSPC,5); break; }
        acquisition_lock_marker(); ram_log[g_logged]=r; ++g_logged; ++next[r.sensor]; g_hash=hash(g_hash,&r); CHECK(k_mutex_unlock(&log_lock)==0);
    }
    g_logger_done=1; k_sem_give(&log_done);
}
static void reader(void *x,void *y,void *z)
{
    (void)x;(void)y;(void)z;
    CHECK(k_mutex_lock(&log_lock,K_MSEC(10))==0); k_sem_give(&lock_held); k_msleep(30); CHECK(k_mutex_unlock(&log_lock)==0); k_sem_give(&lock_released);
    CHECK(k_sem_take(&start,K_MSEC(1000))==0); CHECK(k_sem_take(&log_done,K_MSEC(10000))==0);
    CHECK(k_mutex_lock(&log_lock,K_MSEC(20))==0); uint32_t next[2]={0},last[2]={0};
    for (uint32_t i=0;i<g_logged;++i) {
        const record *r=&ram_log[i]; CHECK(r->sensor<2 && r->sequence==next[r->sensor] && r->uptime>=last[r->sensor]);
        CHECK(r->checksum==check(r) && r->value==(r->sensor?30000:25000)+(int32_t)r->sequence*(r->sensor?40:25));
        last[r->sensor]=r->uptime; ++next[r->sensor]; ++g_verified; g_read_hash=hash(g_read_hash,r);
    }
    CHECK(k_mutex_unlock(&log_lock)==0); g_reader_done=1;
}
int main(void)
{
    for (uint32_t i=0;i<4;++i) { k_thread_entry_t entry=i<2?producer:i==2?logger:reader; k_thread_create(&threads[i],stacks[i],K_THREAD_STACK_SIZEOF(stacks[i]),entry,(void *)(uintptr_t)i,NULL,NULL,i==2?1:2,0,K_NO_WAIT); }
    CHECK(k_sem_take(&lock_held,K_MSEC(100))==0); int64_t before=k_uptime_get(); CHECK(k_mutex_lock(&log_lock,K_MSEC(5))==-EAGAIN && k_uptime_get()-before>=5); ++g_mutex_timeouts;
    CHECK(k_sem_take(&lock_released,K_MSEC(100))==0);
    if (messages.max_msgs<8U) error(-ENOSPC,3);
    if (SCENARIO==6) error(-EAGAIN,6);
    if (SCENARIO==4) { record dummy={0}; for (int i=0;i<CAPACITY;++i) CHECK(k_msgq_put(&messages,&dummy,K_NO_WAIT)==0); g_peak=CAPACITY; }
    for (unsigned int i=0;i<4;++i) k_sem_give(&start);
    for (unsigned int i=0;i<4;++i) CHECK(k_thread_join(&threads[i],K_MSEC(12000))==0);
    CHECK(g_done_mask==3 && g_reader_done && g_logger_done && g_verified==g_logged && g_hash==g_read_hash);
    if (!SCENARIO) CHECK(!g_error && g_produced[0]==128 && g_produced[1]==128 && g_received==256 && g_logged==256 && g_peak<=CAPACITY);
    else CHECK(g_error!=0);
    size_t main_free; CHECK(k_thread_stack_space_get(k_current_get(),&main_free)==0); stat("stack_main",(uint32_t)main_free);
    stat("scenario",SCENARIO); printk("[STAT] error=%d\n",g_error); stat("location",g_location); stat("produced_a",g_produced[0]); stat("produced_b",g_produced[1]); stat("received",g_received); stat("logged",g_logged); stat("verified",g_verified); stat("hash",g_hash); stat("read_hash",g_read_hash); stat("queue_peak",g_peak); stat("queue_waits",g_queue_waits); stat("mutex_timeouts",g_mutex_timeouts); stat("log_capacity",LOG_CAPACITY); stat("log_bytes",sizeof ram_log); stat("object_bytes",sizeof(messages)+sizeof(log_lock)+sizeof(start)+sizeof(lock_held)+sizeof(lock_released)+sizeof(log_done)+sizeof threads);
    for (uint32_t i=0;i<4;++i) { size_t free; CHECK(k_thread_stack_space_get(&threads[i],&free)==0); char name[]="stack_0"; name[6]=(char)('0'+i); stat(name,(uint32_t)free); }
    stat("uptime",(uint32_t)k_uptime_get()); g_result=g_error?1U:0U; stat("stopped",g_error!=0); stat("result",g_result); acquisition_complete(); vel_exit(g_result?42U:0U); return 0;
}
