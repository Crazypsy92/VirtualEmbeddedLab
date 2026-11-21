#define DT_DRV_COMPAT vnd_vel_virtual_temp
#include "vel_test.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#pragma GCC diagnostic pop
#include <limits.h>
struct vel_config { int32_t initial,step; uint32_t id,fail_after; bool unavailable; };
struct vel_data { struct k_mutex mutex; uint32_t count; int32_t value; bool valid; };
static int fetch(const struct device *dev,enum sensor_channel chan)
{
    if (chan!=SENSOR_CHAN_ALL && chan!=SENSOR_CHAN_AMBIENT_TEMP) return -ENOTSUP;
    const struct vel_config *c=dev->config; struct vel_data *d=dev->data;
    int rc=k_mutex_lock(&d->mutex,K_MSEC(50)); if (rc) return rc;
    if ((c->fail_after && d->count>=c->fail_after) || d->count==UINT32_MAX) rc=-EIO;
    else { d->value=c->initial+(int32_t)(d->count%128U)*c->step; ++d->count; d->valid=true; }
    int unlock=k_mutex_unlock(&d->mutex); return rc ? rc : unlock;
}
static int channel_get(const struct device *dev,enum sensor_channel chan,struct sensor_value *value)
{
    if (value==NULL) return -EINVAL;
    if (chan!=SENSOR_CHAN_AMBIENT_TEMP) return -ENOTSUP;
    struct vel_data *d=dev->data; int rc=k_mutex_lock(&d->mutex,K_MSEC(50)); if (rc) return rc;
    if (!d->valid) rc=-ENODATA;
    else { value->val1=d->value/1000; value->val2=(d->value%1000)*1000; }
    int unlock=k_mutex_unlock(&d->mutex); return rc ? rc : unlock;
}
static int attr_get(const struct device *dev,enum sensor_channel chan,enum sensor_attribute attr,struct sensor_value *value)
{
    if (value==NULL) return -EINVAL;
    if (chan!=SENSOR_CHAN_AMBIENT_TEMP || attr!=SENSOR_ATTR_PRIV_START) return -ENOTSUP;
    struct vel_data *d=dev->data; int rc=k_mutex_lock(&d->mutex,K_MSEC(50)); if (rc) return rc;
    value->val1=(int32_t)(d->count%1000000U); value->val2=0; return k_mutex_unlock(&d->mutex);
}
static int init(const struct device *dev)
{
    const struct vel_config *c=dev->config; struct vel_data *d=dev->data;
    if (c->unavailable) return -ENODEV;
    if (c->initial < -100000 || c->initial>100000 || c->step<0 || c->step>1000 || c->id>255) return -EINVAL;
    k_mutex_init(&d->mutex); return 0;
}
static DEVICE_API(sensor,vel_api)={.sample_fetch=fetch,.channel_get=channel_get,.attr_get=attr_get};
#define DEFINE_SENSOR(i) \
    static struct vel_data data_##i; \
    static const struct vel_config config_##i={DT_INST_PROP(i,initial_millicelsius),DT_INST_PROP(i,step_millicelsius),DT_INST_PROP(i,instance_id),DT_INST_PROP(i,fail_after),DT_INST_PROP(i,unavailable)}; \
    DEVICE_DT_INST_DEFINE(i,init,NULL,&data_##i,&config_##i,POST_KERNEL,CONFIG_SENSOR_INIT_PRIORITY,&vel_api);
DT_INST_FOREACH_STATUS_OKAY(DEFINE_SENSOR)
