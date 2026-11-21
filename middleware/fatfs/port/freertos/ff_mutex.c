#include "vel_runtime.h"
#include "ff.h"
#include "ff_mutex.h"
SemaphoreHandle_t g_fs_mutex[2];
volatile uint32_t g_fs_takes,g_fs_gives,g_fs_timeouts,g_fs_contention;
volatile TaskHandle_t g_fs_owner;
__attribute__((noinline)) void fs_lock_marker(void) { __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void fs_unlock_marker(void) { __asm volatile("nop" ::: "memory"); }
int ff_mutex_create(int volume)
{
    if (volume<0 || volume>1 || g_fs_mutex[volume]!=NULL) { return 0; }
    g_fs_mutex[volume]=xSemaphoreCreateMutex(); return g_fs_mutex[volume]!=NULL;
}
void ff_mutex_delete(int volume)
{
    REQUIRE(volume>=0 && volume<=1 && g_fs_mutex[volume]!=NULL);
    vSemaphoreDelete(g_fs_mutex[volume]); g_fs_mutex[volume]=NULL;
}
int ff_mutex_take(int volume)
{
    if (volume<0 || volume>1 || g_fs_mutex[volume]==NULL) { return 0; }
    TaskHandle_t holder=xSemaphoreGetMutexHolder(g_fs_mutex[volume]);
    if (holder!=NULL && holder!=xTaskGetCurrentTaskHandle()) { ++g_fs_contention; }
    if (xSemaphoreTake(g_fs_mutex[volume],pdMS_TO_TICKS(FF_FS_TIMEOUT))!=pdTRUE) { ++g_fs_timeouts; return 0; }
    ++g_fs_takes; if (volume==0) { g_fs_owner=xTaskGetCurrentTaskHandle(); fs_lock_marker(); } return 1;
}
void ff_mutex_give(int volume)
{
    REQUIRE(volume>=0 && volume<=1 && xSemaphoreGetMutexHolder(g_fs_mutex[volume])==xTaskGetCurrentTaskHandle());
    if (volume==0) { fs_unlock_marker(); g_fs_owner=NULL; }
    ++g_fs_gives; REQUIRE(xSemaphoreGive(g_fs_mutex[volume])==pdTRUE);
}
