/* Stream/lifecycle adaptation of Zephyr samples/subsys/modbus/tcp_gateway.
 * Official public ADU helpers and RTU backend remain the only protocol backend. */
#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/modbus/modbus.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/fdtable.h>
#include <string.h>
#include <errno.h>
#include <zephyr/drivers/uart.h>
#ifndef GW_RUNTIME_MS
#define GW_RUNTIME_MS 300000
#endif
#define CLIENTS 4
#define QUEUE 16
#define RTU_RESPONSE_TIMEOUT_US 500000
#define RTU_MAX_RESPONSE_AGE_MS 1000
#define RTU_RECOVERY_MARGIN_MS 250
#define CLIENT_FRAME_TIMEOUT_MS 1000
#define CLIENT_IDLE_TIMEOUT_MS 30000
struct client {int fd;uint32_t generation;size_t used;uint8_t input[1024];int64_t last,frame_started;};
static struct client clients[CLIENTS];
static atomic_t live_generation[CLIENTS];
struct job {unsigned slot;uint32_t generation;struct modbus_adu adu;int64_t received,start,end;int rc;};
K_MSGQ_DEFINE(requests,sizeof(struct job),QUEUE,8);
K_MSGQ_DEFINE(completed,sizeof(struct job),QUEUE+1,8);
static int backend;
static int64_t recover_after;
static uint32_t received_count,sent_count,rejected,exceptions;
static atomic_t timeouts,stale,active,max_active;

static int backend_init(void)
{
    struct modbus_iface_param param = {
        .mode = MODBUS_MODE_RTU,
        .rx_timeout = RTU_RESPONSE_TIMEOUT_US,
        .serial = { .baud = 115200, .parity = UART_CFG_PARITY_EVEN },
    };
    return modbus_init_client(backend, param);
}

/* RTU has no transaction ID. Even after an early error, do not start another
 * transaction inside the previous request's declared response window. */
static int recover_backend(void)
{
    if (!recover_after) {
        return 0;
    }
    printk("RTU_ISOLATED max_response_age_ms=%d\n", RTU_MAX_RESPONSE_AGE_MS);
    while (k_uptime_get() < recover_after) {
        k_msleep(10);
    }
    (void)modbus_disable(backend);
    const struct device *uart = DEVICE_DT_GET(DT_NODELABEL(uart1));
    unsigned char byte;
    unsigned int drained = 0;
    while (drained < 4096 && uart_poll_in(uart, &byte) == 0) {
        drained++;
    }
    if (drained == 4096 || backend_init() != 0) {
        recover_after = k_uptime_get() + RTU_MAX_RESPONSE_AGE_MS + RTU_RECOVERY_MARGIN_MS;
        return -EIO;
    }
    recover_after = 0;
    printk("RTU_RESYNCHRONIZED drained=%u\n", drained);
    return 0;
}
static void exception(struct modbus_adu*a,uint8_t code){a->fc|=128;a->data[0]=code;a->length=1;}
static void worker(void*a,void*b,void*c){(void)a;(void)b;(void)c;struct job j;
 while(k_uptime_get()<GW_RUNTIME_MS){if(k_msgq_get(&requests,&j,K_MSEC(50)))continue;
  if(atomic_get(&live_generation[j.slot])!=(atomic_val_t)j.generation){atomic_inc(&stale);continue;}
  if (recover_backend()) {
   exception(&j.adu,11);j.rc=-EIO;j.start=j.end=k_uptime_get();
   if(k_msgq_put(&completed,&j,K_MSEC(100)))printk("FATAL completion queue\n");
   continue;
  }
 if(atomic_get(&live_generation[j.slot])!=(atomic_val_t)j.generation){atomic_inc(&stale);continue;}
  j.start=k_uptime_get();int n=atomic_inc(&active)+1;atomic_val_t previous=atomic_get(&max_active);while(n>previous&&!atomic_cas(&max_active,previous,n))previous=atomic_get(&max_active);
  uint8_t unit=j.adu.unit_id,fc=j.adu.fc;
  j.rc=modbus_raw_backend_txn(backend,&j.adu);if(j.rc==0&&(j.adu.unit_id!=unit||(j.adu.fc!=fc&&j.adu.fc!=(fc|128)))){j.adu.unit_id=unit;j.adu.fc=fc;exception(&j.adu,11);j.rc=-EPROTO;}j.end=k_uptime_get();atomic_dec(&active);if(j.rc){recover_after=j.start+RTU_MAX_RESPONSE_AGE_MS+RTU_RECOVERY_MARGIN_MS;}if(j.rc==-ETIMEDOUT)atomic_inc(&timeouts);
  printk("RTU tid=%u slot=%u generation=%u received=%lld start=%lld end=%lld rc=%d issued=1 uncertain=%u\n",j.adu.trans_id,j.slot,j.generation,(long long)j.received,(long long)j.start,(long long)j.end,j.rc,j.rc?1:0);
  if(k_msgq_put(&completed,&j,K_MSEC(100)))printk("FATAL completion queue\n");
 }
}
K_THREAD_DEFINE(rtu_worker,8192,worker,NULL,NULL,NULL,5,0,0);
static void close_client(unsigned i){if(clients[i].fd>=0){atomic_set(&live_generation[i],0);zsock_close(clients[i].fd);clients[i].fd=-1;clients[i].generation++;clients[i].used=0;}}
static int send_response(unsigned i,struct modbus_adu*a){uint8_t wire[260];modbus_raw_put_header(a,wire);memcpy(wire+8,a->data,a->length);size_t n=8+a->length,offset=0;int64_t deadline=k_uptime_get()+100;
 while(offset<n&&k_uptime_get()<deadline){int rc=zsock_send(clients[i].fd,wire+offset,n-offset,ZSOCK_MSG_DONTWAIT);if(rc>0)offset+=(size_t)rc;else if(rc<0&&(errno==EAGAIN||errno==EWOULDBLOCK))k_msleep(1);else break;}
 if(offset!=n){close_client(i);return -EIO;}sent_count++;if(a->fc&128U)exceptions++;printk("TCP_SENT tid=%u slot=%u complete=%lld\n",a->trans_id,i,(long long)k_uptime_get());return 0;}
static void parse(unsigned i){struct client*c=&clients[i];
 while(c->fd>=0&&c->used>=7){unsigned length=sys_get_be16(c->input+4);if(sys_get_be16(c->input+2)!=0||length<2||length>254){printk("MBAP_REJECT slot=%u\n",i);close_client(i);return;}size_t n=6+length;if(c->used<n)return;
  struct job j={.slot=i,.generation=c->generation,.received=k_uptime_get()};modbus_raw_get_header(&j.adu,c->input);if(j.adu.length>sizeof(j.adu.data)){close_client(i);return;}memcpy(j.adu.data,c->input+8,j.adu.length);memmove(c->input,c->input+n,c->used-n);c->used-=n;c->frame_started=c->used?k_uptime_get():0;received_count++;
  printk("TCP_RECEIVED tid=%u slot=%u generation=%u received=%lld queued=%u\n",j.adu.trans_id,i,c->generation,(long long)j.received,k_msgq_num_used_get(&requests));
  if(j.adu.unit_id!=1){exception(&j.adu,10);(void)send_response(i,&j.adu);}
  else if(k_msgq_put(&requests,&j,K_NO_WAIT)){rejected++;exception(&j.adu,6);(void)send_response(i,&j.adu);}
 }
}
static unsigned thread_count;
static void count_thread(const struct k_thread*t,void*a){(void)a;thread_count++;printk("GW_THREAD name=%s configured=%u\n",k_thread_name_get((k_tid_t)t),(unsigned)t->stack_info.size);}
int main(void){
 for(unsigned i=0;i<CLIENTS;i++)clients[i].fd=-1;
 backend=modbus_iface_get_by_name(DEVICE_DT_NAME(DT_NODELABEL(backend)));if(backend_init()){printk("INIT_FAIL\n");return 1;}
 int serv=zsock_socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons(GW_PORT),.sin_addr={.s_addr=htonl(0x7f000001)}};int yes=1;(void)zsock_setsockopt(serv,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof yes);
 if(serv<0||zsock_bind(serv,(struct sockaddr*)&a,sizeof a)||zsock_listen(serv,4)){printk("NET_FAIL errno=%d\n",errno);return 2;}
 (void)zsock_fcntl(serv,ZVFS_F_SETFL,ZVFS_O_NONBLOCK);printk("TCP_READY port=%d rtu=%d clients=4 queue=16 timeout_us=500000\n",GW_PORT,backend);
 int64_t report=1000;
 while(k_uptime_get()<GW_RUNTIME_MS){
  struct job j;while(k_msgq_get(&completed,&j,K_NO_WAIT)==0){if(clients[j.slot].fd>=0&&clients[j.slot].generation==j.generation)(void)send_response(j.slot,&j.adu);else atomic_inc(&stale);}
  struct zsock_pollfd fds[CLIENTS+1]={{.fd=serv,.events=ZSOCK_POLLIN}};for(unsigned i=0;i<CLIENTS;i++){fds[i+1].fd=clients[i].fd;fds[i+1].events=ZSOCK_POLLIN;}
  int rc=zsock_poll(fds,CLIENTS+1,5);if(rc<0){printk("POLL_FAIL errno=%d\n",errno);break;}
  for(unsigned i=0;i<CLIENTS;i++){struct client*c=&clients[i];if(c->fd<0)continue;
   if(fds[i+1].revents&(ZSOCK_POLLERR|ZSOCK_POLLHUP|ZSOCK_POLLNVAL)){close_client(i);continue;}
   if(fds[i+1].revents&ZSOCK_POLLIN){int n=zsock_recv(c->fd,c->input+c->used,sizeof(c->input)-c->used,ZSOCK_MSG_DONTWAIT);if(n<=0){if(n==0||(errno!=EAGAIN&&errno!=EWOULDBLOCK))close_client(i);continue;}c->last=k_uptime_get();if(c->used==0)c->frame_started=c->last;c->used+=(size_t)n;parse(i);if(c->used==sizeof(c->input))close_client(i);}
   if(c->fd>=0&&(k_uptime_get()-c->last>CLIENT_IDLE_TIMEOUT_MS||(c->used&&k_uptime_get()-c->frame_started>CLIENT_FRAME_TIMEOUT_MS)))close_client(i);
  }
  /* Retire descriptors signaled by this poll before allocating a slot.
   * A FIN and its replacement connection can arrive in the same poll. */
  if(fds[0].revents&ZSOCK_POLLIN){int fd=zsock_accept(serv,NULL,NULL);unsigned i;for(i=0;i<CLIENTS;i++)if(clients[i].fd<0)break;if(fd>=0){if(i==CLIENTS)zsock_close(fd);else{clients[i].fd=fd;clients[i].generation++;atomic_set(&live_generation[i],clients[i].generation);clients[i].used=0;clients[i].last=k_uptime_get();(void)zsock_fcntl(fd,ZVFS_F_SETFL,ZVFS_O_NONBLOCK);}}}
  if(k_uptime_get()>=report){thread_count=0;k_thread_foreach(count_thread,NULL);printk("GW_THREAD_COUNT %u\n",thread_count);unsigned connections=0;for(unsigned i=0;i<CLIENTS;i++)if(clients[i].fd>=0)connections++;printk("GW_STATS received=%u sent=%u timeouts=%u rejected=%u stale=%u active=%u max_active=%u queued=%u completed=%u connections=%u exceptions=%u\n",received_count,sent_count,(unsigned)atomic_get(&timeouts),rejected,(unsigned)atomic_get(&stale),(unsigned)atomic_get(&active),(unsigned)atomic_get(&max_active),k_msgq_num_used_get(&requests),k_msgq_num_used_get(&completed),connections,exceptions);report=k_uptime_get()+1000;}
  k_msleep(1);
 }
 for(unsigned i=0;i<CLIENTS;i++){close_client(i);}
 zsock_close(serv);return 0;
}
