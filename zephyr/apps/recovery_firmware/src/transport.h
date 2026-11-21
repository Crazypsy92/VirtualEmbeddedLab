#ifndef VEL_XRCE_TRANSPORT_H
#define VEL_XRCE_TRANSPORT_H
#include <zephyr/kernel.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/sensor.h>
#include <malloc.h>
#include <stdio.h>
#include <zephyr/sys/ring_buffer.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>
#include <uxr/client/profile/transport/custom/custom_transport.h>
#include <std_msgs/msg/int32.h>
static const struct device *const uart=DEVICE_DT_GET(DT_NODELABEL(uart1));
volatile uint32_t g_urx,g_utx,g_command,g_published,g_session,g_errors;
RING_BUF_DECLARE(rx_ring,2048);
K_SEM_DEFINE(rx_ready,0,1);
static void uart_interrupt(const struct device *dev,void *arg)
{
 (void)arg;while(uart_irq_update(dev) && uart_irq_rx_ready(dev)){
  uint8_t bytes[32];int count=uart_fifo_read(dev,bytes,sizeof bytes);
  if(count<=0)break;
  if(ring_buf_put(&rx_ring,bytes,(uint32_t)count)!=(uint32_t)count)++g_errors;
  g_urx+=(uint32_t)count;k_sem_give(&rx_ready);
 }
}
static bool transport_open(struct uxrCustomTransport *t){(void)t;if(!device_is_ready(uart))return false;uart_irq_callback_user_data_set(uart,uart_interrupt,NULL);uart_irq_rx_enable(uart);return true;}
static bool transport_close(struct uxrCustomTransport *t){(void)t;return true;}
__attribute__((noinline)) void xrce_rx_marker(void){__asm volatile("nop" ::: "memory");}
__attribute__((noinline)) void command_marker(void){__asm volatile("nop" ::: "memory");}
static size_t transport_write(struct uxrCustomTransport *t,const uint8_t *buf,size_t len,uint8_t *err)
{
 (void)t;*err=0;for(size_t i=0;i<len;++i)uart_poll_out(uart,buf[i]);g_utx+=(uint32_t)len;return len;
}
static size_t transport_read(struct uxrCustomTransport *t,uint8_t *buf,size_t len,int timeout,uint8_t *err)
{
 (void)t;*err=0;size_t n=ring_buf_get(&rx_ring,buf,(uint32_t)len);
 if(!n && timeout>0){(void)k_sem_take(&rx_ready,K_MSEC(timeout));n=ring_buf_get(&rx_ring,buf,(uint32_t)len);}
 if(n){xrce_rx_marker();}
 return n;
}

#endif
