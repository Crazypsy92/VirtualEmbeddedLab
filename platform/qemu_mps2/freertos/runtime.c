#include "vel_runtime.h"
#include "uart.h"
volatile uint32_t g_tick_hook,g_switches,g_asserts,g_stack_faults,g_hardfaults,g_malloc_failures,g_expect_malloc;
volatile uint32_t g_result=99U;
void vel_stat(const char *key,uint32_t v) { uart_puts("[STAT] "); uart_puts(key); uart_putc('='); uart_u32(v); uart_putc('\n'); }
void vel_trace_switch(void) { ++g_switches; }
void vApplicationTickHook(void) { ++g_tick_hook; }
void vel_finish(uint32_t code)
{
    const uint32_t block[2]={0x20026U,code};
    register uint32_t op __asm("r0")=0x20U;
    register const uint32_t *arg __asm("r1")=block;
    __asm volatile("bkpt 0xab" : "+r"(op) : "r"(arg) : "memory");
    for (;;) { __asm volatile("wfi"); }
}
void vel_assert(const char *file,unsigned int line)
{
    ++g_asserts; uart_puts("[ERROR] Assert "); uart_puts(file); uart_putc(':'); uart_u32(line); uart_putc('\n'); vel_finish(10);
}
void vApplicationStackOverflowHook(TaskHandle_t task,char *name)
{
    (void)task; ++g_stack_faults; uart_puts("[ERROR] StackOverflow "); uart_puts(name); uart_putc('\n'); vel_finish(11);
}
void vApplicationMallocFailedHook(void)
{
    ++g_malloc_failures;
    if (!g_expect_malloc) { uart_puts("[ERROR] MallocFailed\n"); vel_finish(12); }
}
void HardFault_Handler(void) { ++g_hardfaults; uart_puts("[ERROR] HardFault\n"); vel_finish(13); }
void Default_Handler(void) { uart_puts("[ERROR] Default\n"); vel_finish(14); }
__attribute__((noinline)) void task_marker(uint32_t id) { (void)id; __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void vel_complete(void) { __asm volatile("nop" ::: "memory"); }
