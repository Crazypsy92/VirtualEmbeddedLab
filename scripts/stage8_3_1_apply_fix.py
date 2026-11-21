import pathlib,json,sys
R=pathlib.Path(__file__).resolve().parents[1]
if 'static int recover_backend(void)' in (R/'zephyr/apps/modbus_tcp_gateway/src/main.c').read_text():
    sys.exit('RTU recovery is already implemented in the gateway source.')
proof=json.loads((R/'evidence/stage8_3_1/rtu_late/before_fix.json').read_text());assert proof['status']=='FAIL' and proof['defect']=='stale response A accepted for request B'
p=R/'zephyr/apps/modbus_tcp_gateway/src/main.c';s=p.read_text();assert 'recover_after' not in s
s=s.replace('#include <errno.h>','#include <errno.h>\n#include <zephyr/drivers/uart.h>\n#ifndef GW_RUNTIME_MS\n#define GW_RUNTIME_MS 300000\n#endif')
s=s.replace('static int backend;', 'static int backend;static int64_t recover_after;\nstatic int backend_init(void){struct modbus_iface_param p={.mode=MODBUS_MODE_RTU,.rx_timeout=500000,.serial={.baud=115200,.parity=UART_CFG_PARITY_EVEN}};return modbus_init_client(backend,p);}')
block='''if(recover_after){
 printk("RTU_ISOLATED max_response_delay_ms=1000\\n");
 while(k_uptime_get()<recover_after)k_msleep(10);
 (void)modbus_disable(backend);unsigned char discarded;unsigned drained=0;
 while(drained<4096&&uart_poll_in(DEVICE_DT_GET(DT_NODELABEL(uart1)),&discarded)==0)drained++;
 if(drained==4096||backend_init()){exception(&j.adu,11);j.rc=-EIO;j.start=j.end=k_uptime_get();(void)k_msgq_put(&completed,&j,K_MSEC(100));recover_after=k_uptime_get()+750;continue;}
 recover_after=0;printk("RTU_RESYNCHRONIZED bounded_delay_assumption_ms=1000\\n");
 }
 j.start=k_uptime_get();'''
s=s.replace('j.start=k_uptime_get();',block)
s=s.replace('atomic_dec(&active);if(j.rc==-ETIMEDOUT)atomic_inc(&timeouts);','atomic_dec(&active);if(j.rc){recover_after=k_uptime_get()+750;}if(j.rc==-ETIMEDOUT)atomic_inc(&timeouts);')
s=s.replace('k_uptime_get()<300000','k_uptime_get()<GW_RUNTIME_MS').replace('k_uptime_get()-c->last>20000','k_uptime_get()-c->last>30000')
p.write_text(s)
p=R/'zephyr/apps/modbus_tcp_gateway/CMakeLists.txt';p.write_text(p.read_text()+'\nset(GW_RUNTIME_MS 300000 CACHE STRING "Bounded runtime in milliseconds")\ntarget_compile_definitions(app PRIVATE GW_RUNTIME_MS=${GW_RUNTIME_MS})\n')
print('STALE_RESPONSE_FIX_APPLIED')
