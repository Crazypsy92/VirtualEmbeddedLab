#include "uart.h"
#define REG(offset) (*(volatile uint32_t *)(0x40004000UL + (offset)))
int uart_init(void)
{
    REG(8) = 0;
    REG(0x10) = 25000000U / 115200U;
    REG(8) = 1;
    return REG(8) == 1U && REG(0x10) == 217U;
}
void uart_putc(char c)
{
    while ((REG(4) & 1U) != 0U) { }
    REG(0) = (uint32_t)(unsigned char)c;
}
void uart_puts(const char *s)
{
    while (*s != 0) { uart_putc(*s++); }
}
void uart_u32(uint32_t value)
{
    char digits[10];
    unsigned int n = 0;
    do { digits[n++] = (char)('0' + value % 10U); value /= 10U; } while (value != 0U);
    while (n != 0U) { uart_putc(digits[--n]); }
}
