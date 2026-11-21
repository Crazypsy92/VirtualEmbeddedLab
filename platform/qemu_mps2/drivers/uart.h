#ifndef VEL_UART_H
#define VEL_UART_H
#include <stdint.h>
int uart_init(void);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_u32(uint32_t value);
#endif
