#include "vel_test.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/uart.h>
#pragma GCC diagnostic pop
#include "vel_wire.h"
#include <string.h>
static const struct device *const serial=DEVICE_DT_GET(DT_NODELABEL(uart1));
static const struct device *const sensors[]={DEVICE_DT_GET(DT_NODELABEL(sensor_a)),DEVICE_DT_GET(DT_NODELABEL(sensor_b))};
volatile uint32_t g_running,g_period=10,g_sampled,g_sent,g_rx_bytes,g_rx_frames,g_errors,g_commands,g_record_seq[2];
uint8_t g_tx_frame[VEL_FRAME];volatile uint32_t g_tx_length;
static uint8_t rx[VEL_FRAME],last_response[VEL_FRAME];static size_t rx_size,last_length;static bool dropping,have_last;static uint32_t last_seq,last_request_crc;
__attribute__((noinline)) void uart_rx_marker(void) { __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void command_marker(void) { __asm volatile("nop" ::: "memory"); }
__attribute__((noinline)) void uart_tx_marker(void) { __asm volatile("nop" ::: "memory"); }
static void transmit(const vel_packet *p)
{
    size_t n=vel_encode(p,g_tx_frame,sizeof g_tx_frame);CHECK(n>0);g_tx_length=(uint32_t)n;uart_tx_marker();for(size_t i=0;i<n;++i)uart_poll_out(serial,g_tx_frame[i]);
}
static void reply(const vel_packet *request,uint8_t code,bool cache)
{
    vel_packet p={.type=code?VEL_NACK:VEL_ACK,.seq=request->seq,.length=20};
    p.payload[0]=request->type;p.payload[1]=code;p.payload[2]=(uint8_t)g_running;p.payload[3]=0;
    vel_put32(p.payload+4,g_period);vel_put32(p.payload+8,g_sampled);vel_put32(p.payload+12,g_sent);vel_put32(p.payload+16,g_errors);transmit(&p);
    if(cache){memcpy(last_response,g_tx_frame,g_tx_length);last_length=g_tx_length;}
}
static void command(const vel_packet *p)
{
    command_marker();++g_rx_frames;
    if(p->id!=0){reply(p,2,false);return;}
    uint32_t fingerprint=vel_crc(p->payload,p->length)^p->type;
    if(p->seq==0){reply(p,3,false);return;}
    if(have_last && p->seq==last_seq){if(fingerprint==last_request_crc){for(size_t i=0;i<last_length;++i)uart_poll_out(serial,last_response[i]);}else reply(p,3,false);return;}
    if(have_last && (int32_t)(p->seq-last_seq)<=0){reply(p,3,false);return;}
    uint8_t code=0;
    if(p->type==VEL_RATE){if(p->length!=4)code=2;else{uint32_t rate=vel_get32(p->payload);if(rate<10 || rate>200)code=2;else g_period=rate;}}
    else if(p->length!=0)code=2;
    else if(p->type==VEL_START)g_running=1;
    else if(p->type==VEL_STOP)g_running=0;
    else if(p->type!=VEL_STATUS && p->type!=VEL_HELLO)code=4;
    ++g_commands;have_last=true;last_seq=p->seq;last_request_crc=fingerprint;reply(p,code,true);
    if(p->type==VEL_HELLO && code==0){vel_packet hello={.type=VEL_HELLO,.seq=p->seq,.length=4};vel_put32(hello.payload,1);transmit(&hello);}
}
static void receive_error(uint32_t code)
{
    ++g_errors;g_running=0;vel_packet p={.type=VEL_ERROR,.length=4};vel_put32(p.payload,code);transmit(&p);
}
int main(void)
{
    CHECK(device_is_ready(serial) && device_is_ready(sensors[0]) && device_is_ready(sensors[1]));printk("[BOOT] Stage5 UART1 protocol\n");
    int64_t last_rx=k_uptime_get(),next=k_uptime_get(),deadline=k_uptime_get()+60000;
    while(k_uptime_get()<deadline){
        uint8_t byte;unsigned int budget=256;
        while(budget-- && uart_poll_in(serial,&byte)==0){++g_rx_bytes;uart_rx_marker();last_rx=k_uptime_get();
            if(byte==0){if(rx_size && !dropping){vel_packet packet;int code=vel_decode(rx,rx_size,&packet);if(code==0)command(&packet);else receive_error((uint32_t)(-code));}rx_size=0;dropping=false;}
            else if(!dropping){if(rx_size<sizeof rx)rx[rx_size++]=byte;else{dropping=true;rx_size=0;receive_error(5);}}
        }
        if(rx_size && k_uptime_get()-last_rx>300){rx_size=0;receive_error(6);}
        if(g_running && k_uptime_get()>=next){
            for(uint32_t sid=0;sid<2;++sid){if(g_record_seq[sid]>=128)continue;struct sensor_value value;CHECK(sensor_sample_fetch(sensors[sid])==0);CHECK(sensor_channel_get(sensors[sid],SENSOR_CHAN_AMBIENT_TEMP,&value)==0);++g_sampled;
                vel_packet packet={.type=VEL_DATA,.id=(uint8_t)sid,.seq=g_record_seq[sid],.length=8};vel_put32(packet.payload,(uint32_t)k_uptime_get());vel_put32(packet.payload+4,(uint32_t)(value.val1*1000+value.val2/1000));transmit(&packet);++g_sent;++g_record_seq[sid];}
            next=k_uptime_get()+g_period;if(g_record_seq[0]==128 && g_record_seq[1]==128)g_running=0;
        }
        k_msleep(1);
    }
    stat("sampled",g_sampled);stat("sent",g_sent);stat("rx",g_rx_bytes);stat("errors",g_errors);vel_exit(0);return 0;
}
