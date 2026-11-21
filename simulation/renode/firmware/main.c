#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(a))
volatile uint32_t exti_count,rx_count,overflows,timeouts,outputs;
static volatile unsigned head,tail;
static uint8_t ring[128];
extern uint32_t _stack,_sbss,_ebss;
void main(void);
void Default_Handler(void){for(;;)__asm("wfi");}
void Reset_Handler(void){for(uint32_t*p=&_sbss;p<&_ebss;p++)*p=0;main();Default_Handler();}
void EXTI15_10_IRQHandler(void){if(R(0x40010414)&(1<<13)){R(0x40010414)=1<<13;exti_count++;}}
void USART2_IRQHandler(void){if(R(0x40004400)&32){uint8_t c=R(0x40004404);unsigned next=(head+1)%128;if(next==tail)overflows++;else{ring[head]=c;head=next;}rx_count++;}}
__attribute__((section(".vectors"),used)) void(*const vectors[76])(void)={ [0]=(void(*)(void))&_stack,[1]=Reset_Handler,[3]=Default_Handler,[16+38]=USART2_IRQHandler,[16+40]=EXTI15_10_IRQHandler };
__attribute__((noinline)) void gpio_marker(void){__asm volatile("nop");}
__attribute__((noinline)) void tx(uint8_t c){while(!(R(0x40004400)&128)){}R(0x40004404)=c;}
static void text(const char*s){while(*s)tx(*s++);}
void main(void){
 R(0x40021018)|=(1<<0)|(1<<2)|(1<<4);R(0x4002101c)|=1<<17;
 R(0x40010800)=0x44442222;R(0x40011004)=(R(0x40011004)&~(15u<<20))|(4u<<20);
 R(0x40010014)=(R(0x40010014)&~(15u<<4))|(2u<<4);
 R(0x40010400)|=1<<13;R(0x40010408)|=1<<13;R(0x4001040c)|=1<<13;
 R(0x40004408)=0x138;R(0x4000440c)=(1<<13)|(1<<5)|(1<<3)|(1<<2);
 R(0xe000e104)=(1<<6)|(1<<8);__asm volatile("cpsie i");
 for(unsigned i=0;i<1000;i++){outputs=i&15;R(0x4001080c)=outputs;gpio_marker();}
 text("READY\n");unsigned idle=0;unsigned n=0;char buf[64];int overflow=0;
 for(;;){
  if(tail!=head){uint8_t c=ring[tail];tail=(tail+1)%128;idle=0;
   if(c=='\n'){if(overflow){text("ERR overflow\n");overflows++;}else{buf[n]=0;text("ACK ");text(buf);text("\n");}n=0;overflow=0;}
   else if(n<63)buf[n++]=c;else overflow=1;
  }else if(n && ++idle>100000){n=0;overflow=0;timeouts++;idle=0;text("ERR timeout\n");}
 }
}
