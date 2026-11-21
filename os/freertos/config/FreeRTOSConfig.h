#ifndef VEL_FREERTOS_CONFIG_H
#define VEL_FREERTOS_CONFIG_H
#include <stdint.h>
void vel_assert(const char *, unsigned int);
void vel_trace_switch(void);
#define configUSE_PREEMPTION 1
#define configUSE_TIME_SLICING 1
#define configCPU_CLOCK_HZ 25000000UL
#define configTICK_RATE_HZ 1000U
#define configMAX_PRIORITIES 5
#define configMINIMAL_STACK_SIZE 256U
#define configTOTAL_HEAP_SIZE (96U*1024U)
#define configMAX_TASK_NAME_LEN 16
#define configUSE_16_BIT_TICKS 0
#define configIDLE_SHOULD_YIELD 1
#define configUSE_MUTEXES 1
#define configUSE_RECURSIVE_MUTEXES 0
#define configUSE_COUNTING_SEMAPHORES 0
#define configQUEUE_REGISTRY_SIZE 0
#define configUSE_TIMERS 0
#define configUSE_TICK_HOOK 1
#define configUSE_IDLE_HOOK 0
#define configCHECK_FOR_STACK_OVERFLOW 2
#define configUSE_MALLOC_FAILED_HOOK 1
#define configSUPPORT_DYNAMIC_ALLOCATION 1
#define configSUPPORT_STATIC_ALLOCATION 0
#define configUSE_TRACE_FACILITY 1
#define configGENERATE_RUN_TIME_STATS 0
#define configPRIO_BITS 3
#define configKERNEL_INTERRUPT_PRIORITY 255U
#define configMAX_SYSCALL_INTERRUPT_PRIORITY 128U
#define INCLUDE_xTaskGetIdleTaskHandle 1
#define INCLUDE_xSemaphoreGetMutexHolder 1
#define INCLUDE_vTaskDelay 1
#define INCLUDE_vTaskDelete 1
#define INCLUDE_vTaskSuspend 1
#define INCLUDE_uxTaskGetStackHighWaterMark 1
#define INCLUDE_xTaskGetCurrentTaskHandle 1
#define INCLUDE_xTaskGetSchedulerState 1
#define configASSERT(x) do { if (!(x)) vel_assert(__FILE__,__LINE__); } while (0)
#define traceTASK_SWITCHED_IN() vel_trace_switch()
#define vPortSVCHandler SVC_Handler
#define xPortPendSVHandler PendSV_Handler
#define xPortSysTickHandler SysTick_Handler
#endif
