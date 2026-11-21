#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/modbus/modbus.h>
#include <zephyr/sys/byteorder.h>
#include <modbus_internal.h>
static const struct device *gpio=DEVICE_DT_GET(DT_NODELABEL(gpio0));
static const struct device *control=DEVICE_DT_GET(DT_NODELABEL(uart0));
static uint16_t holding[8]={1,10,500,0,100,0,0,0};
static uint32_t requests,valid,responses,errors,crc_errors,exceptions,edges,rising,falling,samples,beats,de_high,de_low;
static struct gpio_callback cb;
static uint8_t bitmap(unsigned start,unsigned count){uint8_t v=0;for(unsigned i=0;i<count;i++)if(gpio_pin_get(gpio,start+i)>0)v|=BIT(i);return v;}
static uint8_t output(void){gpio_port_value_t v=0;(void)gpio_emul_output_get_masked(gpio,255,&v);return v;}
static void change(const struct device*d,struct gpio_callback*c,uint32_t pins){(void)d;(void)c;for(unsigned i=8;i<12;i++)if(pins&BIT(i)){edges++;if(gpio_pin_get(gpio,i))rising++;else falling++;}if(pins&BIT(16)){gpio_port_value_t v=0;(void)gpio_emul_output_get_masked(gpio,BIT(16),&v);if(v&BIT(16))de_high++;else de_low++;}}
static bool range(uint16_t a,uint16_t v){switch(a){case 0:return v<=2;case 1:return v>=1&&v<=1000;case 2:return v<=1000;case 3:return v<=255;case 4:return v>=1&&v<=1000;default:return false;}}
static int coil_rd(uint16_t a,bool*v){if(a>=8)return -ENOTSUP;*v=!!(output()&BIT(a));return 0;}
static int coil_wr(uint16_t a,bool v){if(a>=8)return -ENOTSUP;int rc=gpio_pin_set(gpio,a,v);holding[3]=output();return rc;}
static int di_rd(uint16_t a,bool*v){if(a>=4)return -ENOTSUP;*v=gpio_pin_get(gpio,8+a)>0;return 0;}
static int hr_rd(uint16_t a,uint16_t*v){if(a>=8)return -ENOTSUP;*v=holding[a];return 0;}
static int hr_wr(uint16_t a,uint16_t v){if(a>=5)return -ENOTSUP;if(!range(a,v))return -EINVAL;holding[a]=v;if(a==3)for(unsigned i=0;i<8;i++)(void)gpio_pin_set(gpio,i,!!(v&BIT(i)));return 0;}
static int ir_rd(uint16_t a,uint16_t*v){uint32_t now=(uint32_t)k_uptime_get();switch(a){case 0:*v=holding[0]|((samples>holding[2])?256:0);break;case 1:*v=now;break;case 2:*v=now>>16;break;case 3:*v=requests;break;case 4:*v=responses;break;case 5:*v=errors;break;case 6:*v=bitmap(8,4);break;case 7:*v=output();break;default:return -ENOTSUP;}return 0;}
/* Application validation shim around the pinned official dispatcher. The official
 * UART framing, CRC, standard handlers and response serializer stay unchanged.
 * Preflight prevents the upstream per-item write callbacks from partial commits. */
bool __real_modbus_server_handler(struct modbus_context *ctx);
bool __wrap_modbus_server_handler(struct modbus_context *ctx){
 requests++;struct modbus_adu *p=&ctx->rx_adu;uint8_t ex=0;bool write=p->fc==5||p->fc==6||p->fc==15||p->fc==16;
 if(ctx->rx_adu_err){errors++;if(ctx->rx_adu_err==-EIO)crc_errors++;return __real_modbus_server_handler(ctx);}
 if(p->unit_id!=1&&p->unit_id!=0)return __real_modbus_server_handler(ctx);
 valid++;
 if(write){
  if(p->length<4)ex=3;
  else{unsigned a=sys_get_be16(p->data),qty=(p->fc==5||p->fc==6)?1:sys_get_be16(p->data+2),max=(p->fc==5||p->fc==15)?8:5;
   if(!qty)ex=3;else if(a>=max||qty>max-a)ex=2;
   else if(p->fc==5){if(p->length!=4||(sys_get_be16(p->data+2)!=0&&sys_get_be16(p->data+2)!=0xff00))ex=3;}
   else if(p->fc==6){if(p->length!=4||!range(a,sys_get_be16(p->data+2)))ex=3;}
   else{unsigned bytes=p->fc==15?(qty+7)/8:qty*2;if(p->length!=bytes+5||p->data[4]!=bytes)ex=3;
    else if(p->fc==16)for(unsigned i=0;i<qty;i++)if(!range(a+i,sys_get_be16(p->data+5+2*i)))ex=3;
   }
  }
 }
 if(ex){errors++;exceptions++;ctx->tx_adu=*p;ctx->tx_adu.fc=p->fc|128;ctx->tx_adu.length=1;ctx->tx_adu.data[0]=ex;if(p->unit_id){responses++;return true;}return false;}
 bool result=__real_modbus_server_handler(ctx);if(result){responses++;if(ctx->tx_adu.fc&128){errors++;exceptions++;}else if(write)holding[5]++;}return result;
}
static struct modbus_user_callbacks callbacks={.coil_rd=coil_rd,.coil_wr=coil_wr,.discrete_input_rd=di_rd,.holding_reg_rd=hr_rd,.holding_reg_wr=hr_wr,.input_reg_rd=ir_rd};
static void thread_stats(const struct k_thread *t,void *arg){(void)arg;size_t free=0;int rc=k_thread_stack_space_get(t,&free);printk("THREAD name=%s size=%u unused=%u rc=%d\n",k_thread_name_get((k_tid_t)t),(unsigned)t->stack_info.size,(unsigned)free,rc);}
static void stats(void){size_t unused=0;(void)k_thread_stack_space_get(k_current_get(),&unused);gpio_port_value_t v=0;(void)gpio_emul_output_get_masked(gpio,0x30000,&v);printk("STATS requests=%u valid=%u responses=%u errors=%u crc=%u exceptions=%u edges=%u rising=%u falling=%u samples=%u beats=%u de_high=%u de_low=%u direction=%u di=%u do=%u commands=%u unused=%u\n",requests,valid,responses,errors,crc_errors,exceptions,edges,rising,falling,samples,beats,de_high,de_low,(unsigned)(v&0x30000),bitmap(8,4),output(),holding[5],(unsigned)unused);}
int main(void){
 if(!device_is_ready(gpio)||!device_is_ready(control))return 2;
 for(unsigned i=0;i<8;i++)if(gpio_pin_configure(gpio,i,GPIO_OUTPUT_LOW))return 2;
 for(unsigned i=8;i<12;i++){if(gpio_pin_configure(gpio,i,GPIO_INPUT)||gpio_pin_interrupt_configure(gpio,i,GPIO_INT_EDGE_BOTH))return 2;}
 gpio_init_callback(&cb,change,0xf00|BIT(16));(void)gpio_add_callback(gpio,&cb);
 struct modbus_iface_param p={.mode=MODBUS_MODE_RTU,.server={.unit_id=1,.user_cb=&callbacks},.serial={.baud=115200,.parity=UART_CFG_PARITY_EVEN}};
 int iface=modbus_iface_get_by_name(DEVICE_DT_NAME(DT_NODELABEL(rtu)));int rc=modbus_init_server(iface,p);printk("MODBUS_INIT rc=%d iface=%d software=115200_8E1\n",rc,iface);if(rc)return 2;
 int64_t next=0,heartbeat=0,report=1000;while(k_uptime_get()<120000){
  unsigned char c;while(uart_poll_in(control,&c)==0){if(c>='A'&&c<='P'){unsigned bits=c-'A';for(unsigned i=0;i<4;i++)(void)gpio_emul_input_set(gpio,8+i,!!(bits&BIT(i)));printk("INPUT bits=%u\n",bits);}else if(c=='S'){stats();k_thread_foreach(thread_stats,NULL);}}
  int64_t now=k_uptime_get();if(holding[0]&&now>=next){samples++;next=now+holding[1];}if(now>=heartbeat){beats++;heartbeat=now+holding[4];}if(now>=report){stats();report=now+1000;}k_msleep(1);
 }stats();return 0;
}
