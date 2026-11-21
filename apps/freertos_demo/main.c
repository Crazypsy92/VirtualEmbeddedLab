#include "vel_runtime.h"
#include "queue.h"
#include "semphr.h"
#include "uart.h"
static QueueHandle_t messages;
static SemaphoreHandle_t gate,mutex;
TaskHandle_t worker_handles[2];
static TaskHandle_t coordinator_handle,high_handle;
volatile uint32_t g_workers[2],g_low_started,g_low_resumed,g_high_ran,g_priority_first,g_preempt,g_context_ok,g_shared;
static void high_task(void *arg)
{
    (void)arg; g_priority_first=g_low_started==0U;
    REQUIRE(xSemaphoreTake(gate,100)==pdTRUE); g_high_ran=1;
    uint32_t token=0xCAFEU; REQUIRE(xQueueSend(messages,&token,0)==pdTRUE);
    vTaskSuspend(NULL);
}
static void worker(void *arg)
{
    uint32_t id=(uint32_t)(uintptr_t)arg;
    if (id==0U) { g_low_started=1; REQUIRE(xSemaphoreGive(gate)==pdTRUE); REQUIRE(g_high_ran==1); g_low_resumed=1; }
    REQUIRE(context_roundtrip(id)==0); ++g_context_ok; task_marker(id);
    TickType_t start=xTaskGetTickCount();
    while (xTaskGetTickCount()-start<30U) {
        ++g_workers[id];
    }
    REQUIRE(xSemaphoreTake(mutex,10)==pdTRUE); g_shared+=g_workers[id]; REQUIRE(xSemaphoreGive(mutex)==pdTRUE);
    uint32_t token=id+1U; REQUIRE(xQueueSend(messages,&token,0)==pdTRUE); vTaskSuspend(NULL);
}
static void coordinator(void *arg)
{
    (void)arg;
    REQUIRE(g_low_started==0U && g_high_ran==0U);
    uint32_t n=1,out=0;
    for (uint32_t i=0;i<4;++i) { REQUIRE(xQueueSend(messages,&n,0)==pdTRUE); }
    REQUIRE(xQueueSend(messages,&n,0)==errQUEUE_FULL);
    for (uint32_t i=0;i<4;++i) { REQUIRE(xQueueReceive(messages,&out,0)==pdTRUE && out==1U); }
    REQUIRE(xSemaphoreTake(gate,0)==pdFALSE);
    REQUIRE(xQueueReceive(messages,&out,100)==pdTRUE && out==0xCAFEU);
    g_preempt=g_low_resumed==0U; REQUIRE(g_preempt && g_priority_first);
    TickType_t start=xTaskGetTickCount(); vTaskDelay(50); REQUIRE(xTaskGetTickCount()-start>=50U);
    uint32_t total=0;
    for (uint32_t i=0;i<2;++i) { REQUIRE(xQueueReceive(messages,&out,0)==pdTRUE); total+=out; }
    REQUIRE(total==3U && g_workers[0]>0U && g_workers[1]>0U && g_context_ok==2U);
    REQUIRE(g_shared==g_workers[0]+g_workers[1]); REQUIRE(g_switches>20U && g_tick_hook>=50U);
    g_expect_malloc=1; REQUIRE(pvPortMalloc(configTOTAL_HEAP_SIZE)==NULL); g_expect_malloc=0; REQUIRE(g_malloc_failures==1U);
    vel_stat("priority",g_priority_first); vel_stat("preemption",g_preempt);
    vel_stat("worker_a",g_workers[0]); vel_stat("worker_b",g_workers[1]); vel_stat("context_ok",g_context_ok);
    vel_stat("ticks",g_tick_hook); vel_stat("switches",g_switches); vel_stat("queue_full",1);
    vel_stat("stack_a",(uint32_t)uxTaskGetStackHighWaterMark(worker_handles[0]));
    vel_stat("stack_b",(uint32_t)uxTaskGetStackHighWaterMark(worker_handles[1]));
    vel_stat("stack_high",(uint32_t)uxTaskGetStackHighWaterMark(high_handle)); vel_stat("stack_idle",(uint32_t)uxTaskGetStackHighWaterMark(xTaskGetIdleTaskHandle()));
    vel_stat("stack_monitor",(uint32_t)uxTaskGetStackHighWaterMark(coordinator_handle));
    vel_stat("heap_free",(uint32_t)xPortGetFreeHeapSize()); vel_stat("heap_min",(uint32_t)xPortGetMinimumEverFreeHeapSize());
    vel_stat("malloc_expected",g_malloc_failures);
    REQUIRE(g_asserts==0 && g_stack_faults==0 && g_hardfaults==0);
    g_result=0; vel_stat("result",g_result); vel_complete(); vel_finish(g_result);
}
int main(void)
{
    REQUIRE(uart_init()); messages=xQueueCreate(4,sizeof(uint32_t)); gate=xSemaphoreCreateBinary(); mutex=xSemaphoreCreateMutex(); REQUIRE(messages && gate && mutex);
    REQUIRE(xTaskCreate(coordinator,"Coordinator",768,NULL,3,&coordinator_handle)==pdPASS);
    REQUIRE(xTaskCreate(high_task,"High",384,NULL,2,&high_handle)==pdPASS);
    REQUIRE(xTaskCreate(worker,"WorkerA",512,(void *)(uintptr_t)0,1,&worker_handles[0])==pdPASS);
    REQUIRE(xTaskCreate(worker,"WorkerB",512,(void *)(uintptr_t)1,1,&worker_handles[1])==pdPASS);
    uart_puts("[BOOT] FreeRTOS Cortex-M3\n"); vTaskStartScheduler(); REQUIRE(0); return 1;
}
