#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/uart.h>
#include <string.h>
#include <errno.h>
#define CHECK(x) do { if (!(x)) { printk("FAIL line=%d\n",__LINE__); return 1; } } while (0)
static unsigned edges;
static struct gpio_callback callback;
static void edge(const struct device *d,struct gpio_callback *cb,uint32_t pins)
{ (void)d;(void)cb;if(pins & 0xf00)++edges; }
CAN_MSGQ_DEFINE(rxq,8);
static int gpio_test(void)
{
 const struct device *d=DEVICE_DT_GET(DT_NODELABEL(gpio0));CHECK(device_is_ready(d));
 for(unsigned i=0;i<8;i++)CHECK(gpio_pin_configure(d,i,GPIO_OUTPUT_LOW)==0);
 for(unsigned i=8;i<12;i++) { CHECK(gpio_pin_configure(d,i,GPIO_INPUT)==0);CHECK(gpio_pin_interrupt_configure(d,i,GPIO_INT_EDGE_BOTH)==0); }
 gpio_init_callback(&callback,edge,0xf00);CHECK(gpio_add_callback(d,&callback)==0);
 unsigned expected=0;
 for(unsigned i=0;i<1000;i++) { unsigned pin=i%8;expected^=BIT(pin);CHECK(gpio_pin_toggle(d,pin)==0);gpio_port_value_t value;CHECK(gpio_emul_output_get_masked(d,255,&value)==0);CHECK(value==expected); }
 for(unsigned i=0;i<100;i++) { unsigned pin=8+i%4;unsigned value=(i/4+1)%2;CHECK(gpio_emul_input_set(d,pin,value)==0);CHECK(gpio_pin_get(d,pin)==(int)value); }
 CHECK(edges==100);CHECK(gpio_pin_configure(d,0,GPIO_OUTPUT | GPIO_OPEN_DRAIN)==-ENOTSUP);
 printk("GPIO outputs=8 inputs=4 toggles=1000 edges=%u PASS\n",edges);return 0;
}
static int can_test(void)
{
 const struct device *d=DEVICE_DT_GET(DT_NODELABEL(can_loopback0));CHECK(device_is_ready(d));CHECK(can_set_mode(d,CAN_MODE_LOOPBACK)==0);CHECK(can_start(d)==0);
 struct can_filter standard={.id=0,.mask=0,.flags=0},extended={.id=0,.mask=0,.flags=CAN_FILTER_IDE};
 int a=can_add_rx_filter_msgq(d,&rxq,&standard),b=can_add_rx_filter_msgq(d,&rxq,&extended);CHECK(a>=0 && b>=0);
 for(unsigned i=0;i<1000;i++) {
  struct can_frame tx={.id=(i%2)?0x123400+i:0x100+i%100,.dlc=8,.flags=(i%2)?CAN_FRAME_IDE:0},rx;
  for(unsigned k=0;k<8;k++)tx.data[k]=(i>>(k%4)*8)^k;
  CHECK(can_send(d,&tx,K_MSEC(100),NULL,NULL)==0);CHECK(k_msgq_get(&rxq,&rx,K_MSEC(100))==0);CHECK(rx.id==tx.id && rx.dlc==8 && rx.flags==tx.flags && memcmp(rx.data,tx.data,8)==0);
 }
 struct can_frame rx;CHECK(k_msgq_get(&rxq,&rx,K_MSEC(10))==-EAGAIN);
 struct can_frame bad={.id=1,.dlc=9};CHECK(can_send(d,&bad,K_MSEC(10),NULL,NULL)<0);
 can_remove_rx_filter(d,a);can_remove_rx_filter(d,b);CHECK(can_stop(d)==0);printk("CAN sent=1000 received=1000 exact=1000 PASS\n");return 0;
}
int main(void)
{
 if(gpio_test() || can_test())return 1;
 const struct device *u=DEVICE_DT_GET(DT_NODELABEL(uart1));CHECK(device_is_ready(u));printk("UART_READY\n");
 char line[64];size_t n=0;bool overflow=false;unsigned frames=0,timeouts=0,overflows=0;int64_t last=k_uptime_get(),end=last+120000;
 while(k_uptime_get()<end) {
  unsigned char c;
  if(uart_poll_in(u,&c)==0) {
   last=k_uptime_get();
   if(c=='\n') {
    if(overflow){overflows++;const char *s="ERR overflow\n";while(*s)uart_poll_out(u,*s++);}
    else {line[n]=0;if(strcmp(line,"QUIT")==0){printk("UART frames=%u timeouts=%u overflows=%u DONE\n",frames,timeouts,overflows);return 0;}const char *s="ACK ";while(*s)uart_poll_out(u,*s++);for(size_t i=0;i<n;i++)uart_poll_out(u,line[i]);uart_poll_out(u,'\n');frames++;}
    n=0;overflow=false;
   } else if(n<sizeof(line)-1)line[n++]=c;else overflow=true;
  } else {if((n || overflow) && k_uptime_get()-last>200){n=0;overflow=false;timeouts++;const char *s="ERR timeout\n";while(*s)uart_poll_out(u,*s++);}k_msleep(1);}
 }
 printk("FAIL UART deadline\n");return 1;
}
