#ifndef VEL_TEST_H
#define VEL_TEST_H
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <stdint.h>
#pragma GCC diagnostic pop
static inline void vel_exit(uint32_t code)
{
    const uint32_t block[2]={0x20026U,code};
    register uint32_t op __asm("r0")=0x20U;
    register const uint32_t *arg __asm("r1")=block;
    __asm volatile("bkpt 0xab" : "+r"(op) : "r"(arg) : "memory");
    for (;;) { }
}
#define CHECK(x) do { if (!(x)) { printk("[ERROR] %s:%d %s\n",__FILE__,__LINE__,#x); vel_exit(90); } } while (0)
static inline void stat(const char *name,uint32_t v) { printk("[STAT] %s=%u\n",name,v); }
#endif
