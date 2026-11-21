#include "vel_test.h"
K_MSGQ_DEFINE(queue,sizeof(uint32_t),4,4);
K_SEM_DEFINE(gate,0,1);
K_SEM_DEFINE(done,0,2);
K_MUTEX_DEFINE(mutex);
static struct k_thread workers[2];
K_THREAD_STACK_ARRAY_DEFINE(stacks,2,1024);
volatile uint32_t g_runs[2],g_high_first,g_low_started,g_high_ran,g_preemption,g_timer,g_work,g_result=99;
static void timer_fn(struct k_timer *t) { (void)t; ++g_timer; }
K_TIMER_DEFINE(timer,timer_fn,NULL);
static void work_fn(struct k_work *w) { (void)w; ++g_work; }
K_WORK_DEFINE(work,work_fn);
__attribute__((noinline)) void zephyr_thread_marker(uint32_t id) { (void)id; __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void zephyr_complete(void) { __asm volatile("nop" ::: "memory"); }
static void worker(void *a,void *b,void *c)
{
    (void)b; (void)c; uint32_t id=(uint32_t)(uintptr_t)a;
    if (id==0U) { g_high_first=g_low_started==0; CHECK(k_sem_take(&gate,K_MSEC(100))==0); g_high_ran=1; }
    else { g_low_started=1; k_sem_give(&gate); g_preemption=g_high_ran==1; }
    zephyr_thread_marker(id);
    for (uint32_t i=0;i<8U;++i) { CHECK(k_mutex_lock(&mutex,K_MSEC(20))==0); ++g_runs[id]; CHECK(k_mutex_unlock(&mutex)==0); k_msleep(2); }
    uint32_t value=id+10U; CHECK(k_msgq_put(&queue,&value,K_MSEC(20))==0); k_sem_give(&done);
}
int main(void)
{
    uint32_t v=123,out=0;
    for (unsigned int i=0;i<4;++i) CHECK(k_msgq_put(&queue,&v,K_NO_WAIT)==0);
    CHECK(k_msgq_put(&queue,&v,K_MSEC(2))==-EAGAIN);
    for (unsigned int i=0;i<4;++i) CHECK(k_msgq_get(&queue,&out,K_NO_WAIT)==0 && out==v);
    k_timer_start(&timer,K_MSEC(1),K_MSEC(2)); CHECK(k_work_submit(&work)>=0);
    for (uint32_t i=0;i<2;++i) { k_thread_create(&workers[i],stacks[i],K_THREAD_STACK_SIZEOF(stacks[i]),worker,(void *)(uintptr_t)i,NULL,NULL,i==0?1:2,0,K_NO_WAIT); }
    CHECK(k_sem_take(&done,K_MSEC(500))==0 && k_sem_take(&done,K_MSEC(500))==0);
    for (unsigned int i=0;i<2;++i) CHECK(k_thread_join(&workers[i],K_MSEC(100))==0);
    CHECK(k_msgq_get(&queue,&v,K_NO_WAIT)==0 && k_msgq_get(&queue,&out,K_NO_WAIT)==0 && v+out==21);
    k_timer_stop(&timer); CHECK(g_high_first && g_preemption && g_runs[0]==8 && g_runs[1]==8 && g_timer>1 && g_work==1);
    size_t free0,free1; CHECK(k_thread_stack_space_get(&workers[0],&free0)==0 && k_thread_stack_space_get(&workers[1],&free1)==0);
    stat("worker_a",g_runs[0]); stat("worker_b",g_runs[1]); stat("priority",g_high_first); stat("preemption",g_preemption); stat("timer",g_timer); stat("work",g_work); stat("uptime",(uint32_t)k_uptime_get()); stat("stack_a",(uint32_t)free0); stat("stack_b",(uint32_t)free1);
    size_t main_free,work_free; CHECK(k_thread_stack_space_get(k_current_get(),&main_free)==0); CHECK(k_thread_stack_space_get(&k_sys_work_q.thread,&work_free)==0); stat("stack_main",(uint32_t)main_free); stat("stack_work",(uint32_t)work_free);
    g_result=0; stat("result",g_result); zephyr_complete(); vel_exit(0); return 0;
}
