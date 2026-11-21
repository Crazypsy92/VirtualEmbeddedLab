/* Zephyr's documented NEWLIB_LIBC_CUSTOM_SBRK platform hook; no Newlib changes. */
#include <zephyr/kernel.h>
#include <stdint.h>
#include <errno.h>
#ifdef CONFIG_NEWLIB_LIBC_CUSTOM_SBRK
static uint8_t arena[8192] __aligned(8);
static struct k_spinlock arena_lock;
volatile size_t g_sbrk_used;
void *_sbrk(intptr_t count)
{
 k_spinlock_key_t key=k_spin_lock(&arena_lock);
 size_t used=g_sbrk_used;
 if ((count>=0 && (uintptr_t)count>sizeof arena-used) ||
     (count<0 && count<-(intptr_t)used)) {
  k_spin_unlock(&arena_lock,key);errno=ENOMEM;return (void *)-1;
 }
 void *result=arena+used;
 g_sbrk_used=(size_t)((intptr_t)used+count);
 k_spin_unlock(&arena_lock,key);
 return result;
}
int bounded_heap_check(void)
{
 void *before=_sbrk(0);
 if (_sbrk(8193)!=(void *)-1 || _sbrk(0)!=before)return -1;
 printk("[REC] HEAP_BOUND capacity=8192 overflow_rejected=1\n");
 return 0;
}
#endif
