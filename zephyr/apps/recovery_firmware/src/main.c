#include "transport.h"
#include <zephyr/sys/reboot.h>
#include <vel_recovery_interfaces/msg/record.h>
#include <vel_recovery_interfaces/msg/command.h>
#include <vel_recovery_interfaces/msg/status.h>
enum state {DISCONNECTED,WAITING_AGENT,CONNECTING,CONNECTED,RUNNING,RECOVERING,STOPPED};
volatile uint32_t g_state,g_boot,g_epoch,g_recoveries,g_cleanups,g_cleanup_errors;
static __noinit uint32_t boot_magic,boot_counter;
static const struct device *const sensors[]={DEVICE_DT_GET(DT_NODELABEL(sensor_a)),DEVICE_DT_GET(DT_NODELABEL(sensor_b))};
static rcl_allocator_t alloc;
static rclc_support_t support;static rcl_init_options_t options;static rcl_node_t node;static rcl_publisher_t pubs[2],status_pub;static rcl_subscription_t sub;static rclc_executor_t executor;
static bool opt_ok,support_ok,node_ok,pub_ok[2],status_ok,sub_ok,exec_ok,finish,reboot_requested;
static uint32_t seq[2],physical[2],sampled,published,period=5,limit=128,starts,rates,last_id,last_op,last_rate,last_limit;
static vel_recovery_interfaces__msg__Command incoming;
extern unsigned long __malloc_max_total_mem;
__attribute__((noinline)) void recovery_marker(void){__asm volatile("nop" ::: "memory");}
__attribute__((noinline)) void session_ready_marker(void){__asm volatile("nop" ::: "memory");}
static void state_set(enum state s){g_state=(uint32_t)s;printk("[REC] STATE boot=%u session=%u state=%u\n",g_boot,g_epoch,g_state);recovery_marker();}
static void metrics(const char *phase)
{
 size_t unused=0;if(k_thread_stack_space_get(k_current_get(),&unused))++g_errors;struct mallinfo m=mallinfo();
 printk("[REC] MEMORY phase=%s boot=%u session=%u live=%u arena_peak=%u unused=%u sampled=%u published=%u errors=%u cleanup_errors=%u\n",phase,g_boot,g_epoch,(unsigned)m.uordblks,(unsigned)__malloc_max_total_mem,(unsigned)unused,sampled,published,g_errors,g_cleanup_errors);
}
static int status(uint32_t id,uint32_t op,uint32_t result)
{
 size_t unused=0;(void)k_thread_stack_space_get(k_current_get(),&unused);struct mallinfo m=mallinfo();
 vel_recovery_interfaces__msg__Status msg={.boot_id=g_boot,.session_id=g_epoch,.request_id=id,.opcode=op,.result=result,.state=g_state,.period_ms=period,.sampled=sampled,.published=published,.start_effects=starts,.rate_effects=rates,.errors=g_errors,.heap_live=(uint32_t)m.uordblks,.stack_unused=(uint32_t)unused};
 return (int)rcl_publish(&status_pub,&msg,NULL);
}
static void command(const void *pointer)
{
 const vel_recovery_interfaces__msg__Command *p=pointer;uint32_t result=0;g_command=p->request_id;command_marker();
 if(p->boot_id!=g_boot || p->session_id!=g_epoch)result=6;
 else if(!p->request_id || (last_id && (int32_t)(p->request_id-last_id)<0))result=3;
 else if(p->request_id==last_id){result=(p->opcode==last_op && p->period_ms==last_rate && p->count_per_sensor==last_limit)?1:3;}
 else {
  if(p->opcode==1){if(p->count_per_sensor<1 || p->count_per_sensor>5000)result=2;else{limit=p->count_per_sensor;++starts;state_set(RUNNING);}}
  else if(p->opcode==2)state_set(CONNECTED);
  else if(p->opcode==3){if(p->period_ms>200)result=2;else{period=p->period_ms;++rates;}}
  else if(p->opcode==5){finish=true;state_set(STOPPED);}
  else if(p->opcode==6){reboot_requested=true;state_set(STOPPED);}
  else if(p->opcode!=4)result=4;
  if(result==0){last_id=p->request_id;last_op=p->opcode;last_rate=p->period_ms;last_limit=p->count_per_sensor;}
 }
 if(status(p->request_id,p->opcode,result)!=RCL_RET_OK){++g_errors;state_set(RECOVERING);}
}
#define TRY(expr,flag) do {if((expr)!=RCL_RET_OK){printk("[REC] CREATE_FAIL line=%d\n",__LINE__);return false;}flag=true;}while(0)
static bool create(void)
{
 ++g_epoch;seq[0]=seq[1]=0;
 options=rcl_get_zero_initialized_init_options();node=rcl_get_zero_initialized_node();pubs[0]=rcl_get_zero_initialized_publisher();pubs[1]=rcl_get_zero_initialized_publisher();status_pub=rcl_get_zero_initialized_publisher();sub=rcl_get_zero_initialized_subscription();executor=rclc_executor_get_zero_initialized_executor();memset(&support,0,sizeof support);
 alloc=rcl_get_default_allocator();TRY(rcl_init_options_init(&options,alloc),opt_ok);if(rcl_init_options_set_domain_id(&options,255))return false;
 TRY(rclc_support_init_with_options(&support,0,NULL,&options,&alloc),support_ok);TRY(rclc_node_init_default(&node,"vel_recovery_mcu","",&support),node_ok);
 const char *topics[]={"/vel/recovery/a","/vel/recovery/b"};for(unsigned i=0;i<2;++i){TRY(rclc_publisher_init_default(&pubs[i],&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_recovery_interfaces,msg,Record),topics[i]),pub_ok[i]);}
 TRY(rclc_publisher_init_default(&status_pub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_recovery_interfaces,msg,Status),"/vel/recovery/status"),status_ok);
 TRY(rclc_subscription_init_default(&sub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_recovery_interfaces,msg,Command),"/vel/recovery/command"),sub_ok);
 TRY(rclc_executor_init(&executor,&support.context,1,&alloc),exec_ok);if(rclc_executor_add_subscription(&executor,&sub,&incoming,command,ON_NEW_DATA))return false;
 state_set(CONNECTED);session_ready_marker();metrics("connected");return status(0,0,0)==0;
}
static void cleanup(void)
{
 if(support_ok)(void)rmw_uros_set_context_entity_destroy_session_timeout(rcl_context_get_rmw_context(&support.context),0);
 #define FINI(flag,expr) do{if(flag){if((expr)!=RCL_RET_OK)++g_cleanup_errors;flag=false;}}while(0)
 FINI(exec_ok,rclc_executor_fini(&executor));FINI(sub_ok,rcl_subscription_fini(&sub,&node));FINI(status_ok,rcl_publisher_fini(&status_pub,&node));for(unsigned i=0;i<2;++i){FINI(pub_ok[i],rcl_publisher_fini(&pubs[i],&node));}FINI(node_ok,rcl_node_fini(&node));FINI(support_ok,rclc_support_fini(&support));FINI(opt_ok,rcl_init_options_fini(&options));
 uart_irq_rx_disable(uart);ring_buf_reset(&rx_ring);k_sem_reset(&rx_ready);
 ++g_cleanups;g_session=0;metrics("cleaned");rcl_reset_error();
}
int main(void)
{
#ifdef CONFIG_NEWLIB_LIBC_CUSTOM_SBRK
 extern int bounded_heap_check(void);
 if(bounded_heap_check())return 2;
#endif
 if(boot_magic!=0x71524941U){boot_magic=0x71524941U;boot_counter=0;}g_boot=++boot_counter;printk("[REC] BOOT id=%u\n",g_boot);
 if(!device_is_ready(sensors[0]) || !device_is_ready(sensors[1]))return 2;
 (void)rmw_uros_set_custom_transport(true,NULL,transport_open,transport_close,transport_write,transport_read);state_set(DISCONNECTED);
 const int64_t end=k_uptime_get()+900000;unsigned failures=0;uint32_t backoff=100;
 while(!finish && k_uptime_get()<end && g_epoch<8){
  state_set(WAITING_AGENT);
  if(rmw_uros_ping_agent(100,1)!=RMW_RET_OK){if(++failures>=12){break;}k_msleep(backoff);if(backoff<500)backoff*=2;continue;}
  state_set(CONNECTING);
  if(!create()){cleanup();if(g_cleanup_errors || ++failures>=12)break;k_msleep(200);continue;}
  g_session=1;failures=0;backoff=100;int64_t ping=k_uptime_get()+200,heartbeat=k_uptime_get()+200,next=k_uptime_get();
  while(!finish && !reboot_requested && g_state!=RECOVERING && k_uptime_get()<end){
   rcl_ret_t rc=rclc_executor_spin_some(&executor,RCL_MS_TO_NS(1));if(rc!=RCL_RET_OK && rc!=RCL_RET_TIMEOUT){++g_errors;printk("[REC] EXEC_ERROR rc=%d\n",(int)rc);state_set(RECOVERING);break;}
   if(k_uptime_get()>=ping){if(rmw_uros_ping_agent(200,3)!=RMW_RET_OK){printk("[REC] PING_TIMEOUT\n");state_set(RECOVERING);break;}ping=k_uptime_get()+200;}
   if(k_uptime_get()>=heartbeat){if(status(0,0,0)){printk("[REC] STATUS_ERROR\n");state_set(RECOVERING);break;}heartbeat=k_uptime_get()+200;}
   if(g_state==RUNNING && k_uptime_get()>=next){
    for(unsigned sid=0;sid<2;++sid){if(seq[sid]>=limit)continue;struct sensor_value value;if(sensor_sample_fetch(sensors[sid]) || sensor_channel_get(sensors[sid],SENSOR_CHAN_AMBIENT_TEMP,&value)){++g_errors;state_set(STOPPED);finish=true;break;}
     vel_recovery_interfaces__msg__Record msg={.boot_id=g_boot,.session_id=g_epoch,.sensor_id=sid,.sequence=seq[sid]++,.sample_index=physical[sid]++,.temperature_milli_c=value.val1*1000+value.val2/1000,.uptime_ms=(uint32_t)k_uptime_get()};++sampled;
     if(rcl_publish(&pubs[sid],&msg,NULL)){printk("[REC] PUBLISH_ERROR sid=%u\n",sid);state_set(RECOVERING);break;}++published;
    }
    next=k_uptime_get()+period;if(seq[0]>=limit && seq[1]>=limit)state_set(CONNECTED);
   }
   k_msleep(1);
  }
  if(!finish && !reboot_requested){state_set(RECOVERING);++g_recoveries;}
  cleanup();if(g_cleanup_errors)break;
  if(reboot_requested){printk("[REC] SOFTWARE_REBOOT\n");sys_reboot(SYS_REBOOT_COLD);}
  if(!finish)k_msleep(100);
 }
 state_set(STOPPED);printk("[REC] STOP boot=%u sessions=%u recoveries=%u failures=%u cleanup_errors=%u\n",g_boot,g_epoch,g_recoveries,failures,g_cleanup_errors);return g_cleanup_errors?2:0;
}
