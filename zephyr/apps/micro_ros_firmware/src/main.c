#include "transport.h"
static std_msgs__msg__Int32 input;
static void command(const void *message)
{
 g_command=(uint32_t)((const std_msgs__msg__Int32 *)message)->data;command_marker();printk("[UROS] COMMAND %u\n",g_command);
}
#define CHECK(call) do {int code=(int)(call);if(code){++g_errors;printk("[UROS] ERROR line=%d code=%d %s\n",__LINE__,code,rcl_get_error_string().str);return 2;}}while(0)
int main(void)
{
 printk("[UROS] ARM BOOT Zephyr4.4.2\n");
 CHECK(rmw_uros_set_custom_transport(true,NULL,transport_open,transport_close,transport_write,transport_read));
 if(rmw_uros_ping_agent(500,10)!=RMW_RET_OK){printk("[UROS] NO AGENT\n");return 3;}
 rcl_allocator_t allocator=rcl_get_default_allocator();rclc_support_t support;
 rcl_init_options_t options=rcl_get_zero_initialized_init_options();CHECK(rcl_init_options_init(&options,allocator));
 CHECK(rcl_init_options_set_domain_id(&options,255));
 CHECK(rclc_support_init_with_options(&support,0,NULL,&options,&allocator));g_session=1;
 rcl_node_t node=rcl_get_zero_initialized_node();CHECK(rclc_node_init_default(&node,"vel_micro_ros_mcu","",&support));
 rcl_publisher_t pub=rcl_get_zero_initialized_publisher();CHECK(rclc_publisher_init_default(&pub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs,msg,Int32),"/vel/micro_ros/test"));
 rcl_subscription_t sub=rcl_get_zero_initialized_subscription();CHECK(rclc_subscription_init_default(&sub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs,msg,Int32),"/vel/micro_ros/command"));
 rclc_executor_t exec=rclc_executor_get_zero_initialized_executor();CHECK(rclc_executor_init(&exec,&support.context,1,&allocator));CHECK(rclc_executor_add_subscription(&exec,&sub,&input,command,ON_NEW_DATA));
 printk("[UROS] SESSION READY\n");int64_t end=k_uptime_get()+30000;std_msgs__msg__Int32 out={0};
 while(k_uptime_get()<end){out.data=(int32_t)++g_published;CHECK(rcl_publish(&pub,&out,NULL));rcl_ret_t code=rclc_executor_spin_some(&exec,RCL_MS_TO_NS(20));if(code!=RCL_RET_OK && code!=RCL_RET_TIMEOUT){++g_errors;break;}k_msleep(80);}
 size_t unused=0;CHECK(k_thread_stack_space_get(k_current_get(),&unused));struct mallinfo info=mallinfo();printk("[UROS] RESOURCE stack_unused=%u heap_used=%u arena=%u published=%u command=%u\n",(unsigned)unused,(unsigned)info.uordblks,(unsigned)info.arena,g_published,g_command);
 CHECK(rmw_uros_set_context_entity_destroy_session_timeout(rcl_context_get_rmw_context(&support.context),0));CHECK(rclc_executor_fini(&exec));CHECK(rcl_subscription_fini(&sub,&node));CHECK(rcl_publisher_fini(&pub,&node));CHECK(rcl_node_fini(&node));CHECK(rclc_support_fini(&support));CHECK(rcl_init_options_fini(&options));printk("[UROS] FINI\n");return g_errors?2:0;
}
