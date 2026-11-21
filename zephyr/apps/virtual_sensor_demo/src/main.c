#include "vel_test.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#pragma GCC diagnostic pop
volatile uint32_t g_sensor_samples,g_concurrent_samples,g_result=99;
__attribute__((noinline)) void sensor_complete(void) { __asm volatile("nop" ::: "memory"); }
#if CONFIG_VEL_VIRTUAL_SENSOR
static const struct device *const a=DEVICE_DT_GET(DT_NODELABEL(sensor_a));
static const struct device *const b=DEVICE_DT_GET(DT_NODELABEL(sensor_b));
static const struct device *const bad=DEVICE_DT_GET(DT_NODELABEL(sensor_bad));
K_THREAD_STACK_ARRAY_DEFINE(stacks,2,1024);
static struct k_thread threads[2];
static void concurrent(void *x,void *y,void *z)
{
    (void)x;(void)y;(void)z;
    for (unsigned int i=0;i<40;++i) { struct sensor_value value; CHECK(sensor_sample_fetch(a)==0); CHECK(sensor_channel_get(a,SENSOR_CHAN_AMBIENT_TEMP,&value)==0); CHECK(value.val1>=25 && value.val1<=28); k_msleep(1); }
}
#endif
int main(void)
{
#if CONFIG_VEL_VIRTUAL_SENSOR
    CHECK(device_is_ready(a) && device_is_ready(b) && !device_is_ready(bad));
    struct sensor_value value;
    CHECK(sensor_channel_get(a,SENSOR_CHAN_AMBIENT_TEMP,&value)==-ENODATA);
    CHECK(sensor_sample_fetch_chan(a,SENSOR_CHAN_ACCEL_X)==-ENOTSUP);
    CHECK(sensor_channel_get(a,SENSOR_CHAN_ACCEL_X,&value)==-ENOTSUP);
    CHECK(sensor_channel_get(a,SENSOR_CHAN_AMBIENT_TEMP,NULL)==-EINVAL);
    for (uint32_t i=0;i<16;++i) {
        CHECK(sensor_sample_fetch(a)==0 && sensor_channel_get(a,SENSOR_CHAN_AMBIENT_TEMP,&value)==0);
        CHECK(value.val1*1000+value.val2/1000==25000+(int32_t)i*25); ++g_sensor_samples;
    }
    CHECK(sensor_sample_fetch(b)==0 && sensor_channel_get(b,SENSOR_CHAN_AMBIENT_TEMP,&value)==0 && value.val1==30 && value.val2==0); ++g_sensor_samples;
    CHECK(sensor_attr_get(b,SENSOR_CHAN_AMBIENT_TEMP,SENSOR_ATTR_PRIV_START,&value)==0 && value.val1==1);
    for (uint32_t i=0;i<2;++i) k_thread_create(&threads[i],stacks[i],K_THREAD_STACK_SIZEOF(stacks[i]),concurrent,NULL,NULL,NULL,2,0,K_NO_WAIT);
    for (uint32_t i=0;i<2;++i) CHECK(k_thread_join(&threads[i],K_MSEC(1000))==0);
    CHECK(sensor_attr_get(a,SENSOR_CHAN_AMBIENT_TEMP,SENSOR_ATTR_PRIV_START,&value)==0 && value.val1==96); g_concurrent_samples=80;
    CHECK(sensor_attr_get(b,SENSOR_CHAN_AMBIENT_TEMP,SENSOR_ATTR_PRIV_START,&value)==0 && value.val1==1);
    stat("samples",g_sensor_samples); stat("concurrent",g_concurrent_samples); stat("unavailable",!device_is_ready(bad));
#else
    stat("driver_disabled",1);
#endif
    g_result=0; stat("result",0); sensor_complete(); vel_exit(0); return 0;
}
