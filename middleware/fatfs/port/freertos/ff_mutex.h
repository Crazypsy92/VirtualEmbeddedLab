#ifndef VEL_FF_MUTEX_H
#define VEL_FF_MUTEX_H
#include "semphr.h"
extern SemaphoreHandle_t g_fs_mutex[2];
extern volatile uint32_t g_fs_takes,g_fs_gives,g_fs_timeouts,g_fs_contention;
extern volatile TaskHandle_t g_fs_owner;
#endif
