#include "transport.h"
#include <vel_micro_interfaces/msg/record.h>
#include <vel_micro_interfaces/msg/command.h>
#include <vel_micro_interfaces/msg/ack.h>
static const struct device *const sensors[]={DEVICE_DT_GET(DT_NODELABEL(sensor_a)),DEVICE_DT_GET(DT_NODELABEL(sensor_b))};
static rcl_publisher_t ack_pub;
static vel_micro_interfaces__msg__Command control_message;
static vel_micro_interfaces__msg__Ack last_ack;
static uint32_t last_request,last_opcode,last_period,sequence[2],sampled,running,period=20,heap_peak;
static bool have_last,finished;
static int callback_error;
__attribute__((noinline)) void sensor_publish_marker(void){__asm volatile("nop" ::: "memory");}
extern unsigned long __malloc_max_total_mem;
static void resources(void)
{
 struct mallinfo info=mallinfo();if((uint32_t)info.uordblks>heap_peak)heap_peak=(uint32_t)info.uordblks;
 size_t unused=0;if(k_thread_stack_space_get(k_current_get(),&unused)!=0){++g_errors;}
 printk("[UROS] RESOURCE sampled=%u published=%u running=%u period=%u errors=%u stack_unused=%u heap_used=%u heap_peak_sampled=%u arena=%u heap_arena_peak=%u\n",sampled,g_published,running,period,g_errors,(unsigned)unused,(unsigned)info.uordblks,heap_peak,(unsigned)info.arena,(unsigned)__malloc_max_total_mem);
}
static void command(const void *ptr)
{
 const vel_micro_interfaces__msg__Command *p=ptr;g_command=p->request_id;command_marker();
 vel_micro_interfaces__msg__Ack ack={.request_id=p->request_id,.opcode=p->opcode};
 bool duplicate=have_last && p->request_id==last_request && p->opcode==last_opcode && p->period_ms==last_period;
 if(duplicate){ack=last_ack;}
 else {
  if(!p->request_id || (have_last && (int32_t)(p->request_id-last_request)<=0))ack.result=3;
  else if(p->opcode==1)running=1;
  else if(p->opcode==2)running=0;
  else if(p->opcode==3){if(p->period_ms<10 || p->period_ms>200)ack.result=2;else period=p->period_ms;}
  else if(p->opcode==5){finished=true;running=0;}
  else if(p->opcode!=4)ack.result=4;
  ack.running=(bool)running;ack.period_ms=period;ack.sampled=sampled;ack.published=g_published;ack.errors=g_errors;
  if(!have_last || (int32_t)(p->request_id-last_request)>0){last_ack=ack;last_request=p->request_id;last_opcode=p->opcode;last_period=p->period_ms;have_last=true;}
 }
 if(rcl_publish(&ack_pub,&ack,NULL)!=RCL_RET_OK){callback_error=1;++g_errors;}
 printk("[UROS] ACK request=%u opcode=%u result=%u running=%u sampled=%u published=%u duplicate=%u\n",ack.request_id,ack.opcode,ack.result,(unsigned)ack.running,ack.sampled,ack.published,(unsigned)duplicate);
 resources();
}
#define CHECK(call) do {int code=(int)(call);if(code){++g_errors;printk("[UROS] ERROR line=%d code=%d %s\n",__LINE__,code,rcl_get_error_string().str);return 2;}}while(0)
int main(void)
{
 printk("[UROS] ACQUISITION BOOT Zephyr4.4.2\n");
 if(!device_is_ready(sensors[0]) || !device_is_ready(sensors[1]))return 2;
 CHECK(rmw_uros_set_custom_transport(true,NULL,transport_open,transport_close,transport_write,transport_read));
 if(rmw_uros_ping_agent(300,8)!=RMW_RET_OK){printk("[UROS] DISCONNECTED NO_AGENT\n");return 3;}
 rcl_allocator_t allocator=rcl_get_default_allocator();rcl_init_options_t options=rcl_get_zero_initialized_init_options();CHECK(rcl_init_options_init(&options,allocator));CHECK(rcl_init_options_set_domain_id(&options,255));
 rclc_support_t support;CHECK(rclc_support_init_with_options(&support,0,NULL,&options,&allocator));g_session=1;
 rcl_node_t node=rcl_get_zero_initialized_node();CHECK(rclc_node_init_default(&node,"vel_micro_ros_acquisition","",&support));
 rcl_publisher_t pubs[2]={rcl_get_zero_initialized_publisher(),rcl_get_zero_initialized_publisher()};ack_pub=rcl_get_zero_initialized_publisher();
 const char *topics[]={"/vel/micro_ros/sensor/a","/vel/micro_ros/sensor/b"};
 for(unsigned i=0;i<2;++i)CHECK(rclc_publisher_init_default(&pubs[i],&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_micro_interfaces,msg,Record),topics[i]));
 CHECK(rclc_publisher_init_default(&ack_pub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_micro_interfaces,msg,Ack),"/vel/micro_ros/ack"));
 rcl_subscription_t sub=rcl_get_zero_initialized_subscription();CHECK(rclc_subscription_init_default(&sub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(vel_micro_interfaces,msg,Command),"/vel/micro_ros/command"));
 rclc_executor_t exec=rclc_executor_get_zero_initialized_executor();CHECK(rclc_executor_init(&exec,&support.context,1,&allocator));CHECK(rclc_executor_add_subscription(&exec,&sub,&control_message,command,ON_NEW_DATA));
 printk("[UROS] ACQUISITION READY\n");resources();int64_t end=k_uptime_get()+60000,next=k_uptime_get(),ping=k_uptime_get()+500;
 while(!finished && k_uptime_get()<end){
  rcl_ret_t rc=rclc_executor_spin_some(&exec,RCL_MS_TO_NS(5));if(rc!=RCL_RET_OK && rc!=RCL_RET_TIMEOUT){++g_errors;printk("[UROS] ERROR EXECUTOR\n");break;}
  if(k_uptime_get()>=ping){if(rmw_uros_ping_agent(100,2)!=RMW_RET_OK){++g_errors;running=0;printk("[UROS] DISCONNECTED AGENT_LOST\n");break;}ping=k_uptime_get()+500;}
  if(running && k_uptime_get()>=next){
   for(unsigned sid=0;sid<2;++sid){
    if(sequence[sid]>=128){continue;}
    struct sensor_value v;
    CHECK(sensor_sample_fetch(sensors[sid]));CHECK(sensor_channel_get(sensors[sid],SENSOR_CHAN_AMBIENT_TEMP,&v));++sampled;
    vel_micro_interfaces__msg__Record data={.sensor_id=(uint8_t)sid,.sequence=sequence[sid],.temperature_milli_c=v.val1*1000+v.val2/1000,.uptime_ms=(uint32_t)k_uptime_get()};sensor_publish_marker();
    rc=rcl_publish(&pubs[sid],&data,NULL);if(rc!=RCL_RET_OK){++g_errors;running=0;printk("[UROS] DISCONNECTED PUBLISH_FAILED\n");break;}++g_published;++sequence[sid];
   }
   next=k_uptime_get()+period;if(sequence[0]==128 && sequence[1]==128)running=0;
  }
  struct mallinfo memory=mallinfo();if((uint32_t)memory.uordblks>heap_peak)heap_peak=(uint32_t)memory.uordblks;
  k_msleep(1);
 }
 resources();CHECK(rmw_uros_set_context_entity_destroy_session_timeout(rcl_context_get_rmw_context(&support.context),0));CHECK(rclc_executor_fini(&exec));CHECK(rcl_subscription_fini(&sub,&node));CHECK(rcl_publisher_fini(&ack_pub,&node));for(unsigned i=0;i<2;++i)CHECK(rcl_publisher_fini(&pubs[i],&node));CHECK(rcl_node_fini(&node));CHECK(rclc_support_fini(&support));CHECK(rcl_init_options_fini(&options));resources();printk("[UROS] ACQUISITION FINI\n");return g_errors || callback_error?2:0;
}
