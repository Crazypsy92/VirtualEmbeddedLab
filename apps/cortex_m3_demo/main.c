#include <stdint.h>
#include "uart.h"
#define MMIO(addr) (*(volatile uint32_t *)(addr))
volatile uint32_t data_probe[4] = {0x12345678U, 0xABCDEF01U, 0x55AA55AAU, 0xC003C003U};
volatile uint32_t bss_probe[16];
volatile uint32_t ticks, svc_count, pendsv_count, exception_failures;
volatile uint32_t svc_msp_seen, svc_psp_seen, last_svc_ipsr, last_pendsv_ipsr;
volatile uint32_t last_svc_exc_return, last_pendsv_exc_return, last_svc_frame, last_pendsv_frame;
volatile uint32_t pendsv_pending_seen, startup_ok, completion_status = 99U;
_Alignas(8) static uint32_t psp_stack[256];
extern uint32_t _stack_limit, _stack_top;
uint32_t svc_psp_call(uint32_t value, uint32_t stack);
static uint32_t ipsr(void) { uint32_t r; __asm volatile ("mrs %0, ipsr" : "=r"(r)); return r; }
static int frame_ok(const uint32_t *frame, uint32_t exc_return)
{
    uintptr_t a = (uintptr_t)frame;
    uintptr_t lo = (exc_return & 4U) != 0U ? (uintptr_t)psp_stack : (uintptr_t)&_stack_limit;
    uintptr_t hi = (exc_return & 4U) != 0U ? (uintptr_t)(psp_stack + 256) : (uintptr_t)&_stack_top;
    return a >= lo && a + 32U <= hi && (a & 7U) == 0U && (frame[7] & 0x01000000U) != 0U && (frame[7] & 0x1FFU) == 0U && frame[6] < 0x00400000U;
}
void svc_dispatch(uint32_t *frame, uint32_t exc_return)
{
    ++svc_count;
    last_svc_ipsr = ipsr();
    last_svc_exc_return = exc_return;
    last_svc_frame = (uint32_t)(uintptr_t)frame;
    if (!frame_ok(frame, exc_return) || last_svc_ipsr != 11U) { ++exception_failures; return; }
    const uint16_t *instruction = (const uint16_t *)(uintptr_t)(frame[6] - 2U);
    if (*instruction != 0xDF2AU || frame[0] != 0x13579BDFU) { ++exception_failures; }
    if (exc_return == 0xFFFFFFF9U) { ++svc_msp_seen; }
    else if (exc_return == 0xFFFFFFFDU) { ++svc_psp_seen; }
    else { ++exception_failures; }
    frame[0] ^= 0xA5A5A5A5U;
}
void pendsv_dispatch(uint32_t *frame, uint32_t exc_return)
{
    ++pendsv_count;
    last_pendsv_ipsr = ipsr();
    last_pendsv_exc_return = exc_return;
    last_pendsv_frame = (uint32_t)(uintptr_t)frame;
    if (!frame_ok(frame, exc_return) || last_pendsv_ipsr != 14U || exc_return != 0xFFFFFFF9U) { ++exception_failures; }
}
void SysTick_Handler(void) { ++ticks; }
__attribute__((noreturn)) static void finish(uint32_t code)
{
    const uint32_t block[2] = {0x20026U, code};
    register uint32_t op __asm ("r0") = 0x20U;
    register const uint32_t *arg __asm ("r1") = block;
    __asm volatile ("bkpt 0xab" : "+r"(op) : "r"(arg) : "memory");
    for (;;) { __asm volatile ("wfi"); }
}
void Default_Handler(void) { uart_puts("[FAULT] Default\n"); finish(2); }
void HardFault_Handler(void) { uart_puts("[FAULT] HardFault\n"); finish(3); }
__attribute__((noinline)) void completion_marker(void) { __asm volatile ("nop" ::: "memory"); }
int main(void)
{
    int ok = uart_init();
    uart_puts("[BOOT] Cortex-M3 Starting\n");
    const uint32_t expected[4] = {0x12345678U, 0xABCDEF01U, 0x55AA55AAU, 0xC003C003U};
    for (unsigned int i = 0; i < 4U; ++i) { if (data_probe[i] != expected[i]) { ok = 0; } }
    for (unsigned int i = 0; i < 16U; ++i) { if (bss_probe[i] != 0U) { ok = 0; } }
    startup_ok = (uint32_t)ok;
    uart_puts(ok ? "[INIT] Data/BSS OK\n[UART] PASS\n" : "[INIT] FAIL\n");
    register uint32_t result __asm ("r0") = 0x13579BDFU;
    __asm volatile ("svc #42" : "+r"(result) :: "r1", "r2", "r3", "r12", "cc", "memory");
    if (result != (0x13579BDFU ^ 0xA5A5A5A5U)) { ok = 0; }
    result = svc_psp_call(0x13579BDFU, (uint32_t)(uintptr_t)(psp_stack + 256));
    if (result != (0x13579BDFU ^ 0xA5A5A5A5U)) { ok = 0; }
    __asm volatile ("cpsid i" ::: "memory");
    MMIO(0xE000ED04UL) = 1U << 28;
    __asm volatile ("dsb\nisb" ::: "memory");
    pendsv_pending_seen = (MMIO(0xE000ED04UL) >> 28) & 1U;
    __asm volatile ("cpsie i\nisb" ::: "memory");
    while (pendsv_count == 0U) { __asm volatile ("nop"); }
    MMIO(0xE000E014UL) = 25000U - 1U;
    MMIO(0xE000E018UL) = 0;
    MMIO(0xE000E010UL) = 7;
    while (ticks < 1U) { __asm volatile ("wfi"); }
    const uint32_t first_tick = ticks;
    uart_puts("[TICK] first="); uart_u32(first_tick); uart_putc('\n');
    while (ticks < first_tick + 4U) { __asm volatile ("wfi"); }
    MMIO(0xE000E010UL) = 0;
    uart_puts("[TICK] final="); uart_u32(ticks); uart_putc('\n');
    uart_puts("[SVC] count="); uart_u32(svc_count);
    uart_puts(" msp="); uart_u32(svc_msp_seen); uart_puts(" psp="); uart_u32(svc_psp_seen); uart_putc('\n');
    uart_puts("[PENDSV] count="); uart_u32(pendsv_count);
    uart_puts(" pending="); uart_u32(pendsv_pending_seen); uart_putc('\n');
    uart_puts("[EXCEPTION] failures="); uart_u32(exception_failures); uart_putc('\n');
    if (svc_count != 2U || svc_msp_seen != 1U || svc_psp_seen != 1U || pendsv_count != 1U || pendsv_pending_seen != 1U || exception_failures != 0U || ticks <= first_tick) { ok = 0; }
    completion_status = ok ? 0U : 1U;
    uart_puts(ok ? "[MAIN] PASS\n" : "[MAIN] FAIL\n");
    completion_marker();
    finish(completion_status);
}
