#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>
#include <std_msgs/msg/int32.h>
static rcl_publisher_t ack_pub;
static unsigned int received;
static int callback_failed;
static void command(const void *ptr)
{
    const std_msgs__msg__Int32 *in=ptr;
    std_msgs__msg__Int32 ack={.data=in->data};
    if(rcl_publish(&ack_pub,&ack,NULL)!=RCL_RET_OK)callback_failed=1;
    ++received;printf("HOST_COMMAND %d\n",in->data);fflush(stdout);
}
#define REQUIRE(expr) do {int code=(int)(expr);if(code!=0){fprintf(stderr,"ERROR %s code=%d line=%d\n",#expr,code,__LINE__);return 2;}}while(0)
int main(int argc,char **argv)
{
    if(argc!=3)return 2;
    setvbuf(stdout,NULL,_IOLBF,0);
    rcl_allocator_t allocator=rcl_get_default_allocator();
    rcl_init_options_t options=rcl_get_zero_initialized_init_options();
    REQUIRE(rcl_init_options_init(&options,allocator));
    REQUIRE(rcl_init_options_set_domain_id(&options,(size_t)strtoul(argv[2],NULL,10)));
    rmw_init_options_t *rmw_options=rcl_init_options_get_rmw_init_options(&options);
    REQUIRE(rmw_uros_options_set_udp_address("127.0.0.1",argv[1],rmw_options));
    REQUIRE(rmw_uros_ping_agent_options(200,5,rmw_options));
    rclc_support_t support;
    REQUIRE(rclc_support_init_with_options(&support,0,NULL,&options,&allocator));
    rcl_node_t node=rcl_get_zero_initialized_node();
    REQUIRE(rclc_node_init_default(&node,"vel_micro_ros_host","",&support));
    rcl_publisher_t pub=rcl_get_zero_initialized_publisher();ack_pub=rcl_get_zero_initialized_publisher();
    REQUIRE(rclc_publisher_init_default(&pub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs,msg,Int32),"/vel/micro_ros/host/test"));
    REQUIRE(rclc_publisher_init_default(&ack_pub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs,msg,Int32),"/vel/micro_ros/host/ack"));
    rcl_subscription_t sub=rcl_get_zero_initialized_subscription();
    REQUIRE(rclc_subscription_init_default(&sub,&node,ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs,msg,Int32),"/vel/micro_ros/host/command"));
    rclc_executor_t executor=rclc_executor_get_zero_initialized_executor();
    REQUIRE(rclc_executor_init(&executor,&support.context,1,&allocator));
    std_msgs__msg__Int32 in={0},out={0};
    REQUIRE(rclc_executor_add_subscription(&executor,&sub,&in,command,ON_NEW_DATA));
    puts("HOST_SESSION_READY");unsigned int published=0;int lost=0;
    for(unsigned int i=0;i<300;++i){
        if(i%5==0 && rmw_uros_ping_agent(100,1)!=RMW_RET_OK){puts("AGENT_LOST");lost=1;break;}
        out.data=(int32_t)++published;
        rcl_ret_t rc=rcl_publish(&pub,&out,NULL);
        if(rc!=RCL_RET_OK){rcl_reset_error();puts("PUBLISH_ERROR");lost=1;break;}
        rc=rclc_executor_spin_some(&executor,RCL_MS_TO_NS(20));
        if(rc!=RCL_RET_OK && rc!=RCL_RET_TIMEOUT){rcl_reset_error();puts("EXECUTOR_ERROR");lost=1;break;}
        struct timespec delay={.tv_sec=0,.tv_nsec=80000000};nanosleep(&delay,NULL);
    }
    REQUIRE(rmw_uros_set_context_entity_destroy_session_timeout(rcl_context_get_rmw_context(&support.context),0));
    REQUIRE(rclc_executor_fini(&executor));REQUIRE(rcl_subscription_fini(&sub,&node));
    REQUIRE(rcl_publisher_fini(&ack_pub,&node));REQUIRE(rcl_publisher_fini(&pub,&node));
    REQUIRE(rcl_node_fini(&node));REQUIRE(rclc_support_fini(&support));REQUIRE(rcl_init_options_fini(&options));
    printf("HOST_FINI published=%u received=%u lost=%d callback_failed=%d\n",published,received,lost,callback_failed);
    return received>0 && lost && !callback_failed?0:3;
}
