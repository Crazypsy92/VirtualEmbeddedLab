#ifndef VEL_RUNTIME_H
#define VEL_RUNTIME_H
#include "FreeRTOS.h"
#include "task.h"
#include <stdint.h>
extern volatile uint32_t g_tick_hook,g_switches,g_result,g_asserts,g_stack_faults,g_hardfaults,g_malloc_failures,g_expect_malloc;
void vel_stat(const char *,uint32_t);
void vel_finish(uint32_t) __attribute__((noreturn));
void vel_complete(void);
void task_marker(uint32_t id);
uint32_t context_roundtrip(uint32_t);
#define REQUIRE(x) do { if (!(x)) vel_assert(__FILE__,__LINE__); } while (0)
#endif
