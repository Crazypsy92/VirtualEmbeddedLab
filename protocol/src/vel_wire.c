#include "vel_wire.h"
#include <string.h>
void vel_put32(uint8_t *p,uint32_t v) { for (unsigned int i=0;i<4;++i) p[i]=(uint8_t)(v>>(8U*i)); }
uint32_t vel_get32(const uint8_t *p) { uint32_t v=0;for(unsigned int i=0;i<4;++i)v|=(uint32_t)p[i]<<(8U*i);return v; }
uint32_t vel_crc(const uint8_t *p,size_t n)
{
    uint32_t c=0xffffffffU;
    for(size_t i=0;i<n;++i){c^=p[i];for(unsigned int j=0;j<8;++j)c=(c>>1)^((c&1U)?0xedb88320U:0U);}
    return c^0xffffffffU;
}
size_t vel_encode(const vel_packet *p,uint8_t *out,size_t capacity)
{
    if(p==NULL || out==NULL || p->length>VEL_PAYLOAD || capacity<VEL_FRAME)return 0;
    uint8_t raw[78];raw[0]=1;raw[1]=p->type;raw[2]=p->id;raw[3]=0;vel_put32(raw+4,p->seq);raw[8]=(uint8_t)p->length;raw[9]=(uint8_t)(p->length>>8);
    memcpy(raw+10,p->payload,p->length);size_t n=10U+p->length;vel_put32(raw+n,vel_crc(raw,n));n+=4;
    size_t code_pos=0,write=1;uint8_t code=1;
    for(size_t i=0;i<n;++i){if(raw[i]==0){out[code_pos]=code;code_pos=write++;code=1;}else{out[write++]=raw[i];++code;}}
    out[code_pos]=code;out[write++]=0;return write;
}
int vel_decode(const uint8_t *input,size_t length,vel_packet *p)
{
    if(input==NULL || p==NULL || length==0 || length>=VEL_FRAME)return -1;
    uint8_t raw[78];size_t i=0,n=0;
    while(i<length){uint8_t c=input[i++];if(c==0 || (size_t)c-1U>length-i)return -1;
        for(unsigned int j=1;j<c;++j){if(n>=sizeof raw || input[i]==0)return -1;raw[n++]=input[i++];}
        if(c!=255U && i<length){if(n>=sizeof raw)return -1;raw[n++]=0;}
    }
    if(n<14)return -2;
    uint16_t size=(uint16_t)((uint16_t)raw[8]|(uint16_t)((uint16_t)raw[9]<<8));
    if(size>VEL_PAYLOAD || n!=14U+size)return -2;
    if(vel_get32(raw+n-4)!=vel_crc(raw,n-4))return -3;
    if(raw[0]!=1 || raw[3]!=0)return -4;
    p->type=raw[1];p->id=raw[2];p->seq=vel_get32(raw+4);p->length=size;memcpy(p->payload,raw+10,size);return 0;
}
