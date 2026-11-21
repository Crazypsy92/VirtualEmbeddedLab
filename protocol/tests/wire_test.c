#include "vel_wire.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"wire failure line %d\n",__LINE__);return 1;}}while(0)
int main(int argc,char **argv)
{
    uint8_t bytes[VEL_FRAME];vel_packet packet={.type=1,.id=0,.seq=1,.length=0},decoded;
    if(argc==3 && strcmp(argv[1],"decode")==0){size_t n=strlen(argv[2]);CHECK(n%2==0 && n/2<VEL_FRAME);for(size_t i=0;i<n/2;++i){unsigned int v;CHECK(sscanf(argv[2]+i*2,"%2x",&v)==1);bytes[i]=(uint8_t)v;}int r=vel_decode(bytes,n/2,&decoded);printf("%d\n",r);return r==0?0:2;}
    if(argc==2 && strcmp(argv[1],"golden")==0){size_t n=vel_encode(&packet,bytes,sizeof bytes);for(size_t i=0;i<n;++i)printf("%02x",bytes[i]);puts("");return 0;}
    CHECK(vel_crc((const uint8_t *)"123456789",9)==0xcbf43926U);
    for(uint16_t n=0;n<=64;++n){packet.length=n;for(uint16_t i=0;i<n;++i)packet.payload[i]=(uint8_t)(i*17U);size_t size=vel_encode(&packet,bytes,sizeof bytes);CHECK(size>0 && bytes[size-1]==0);CHECK(vel_decode(bytes,size-1,&decoded)==0 && decoded.length==n && memcmp(packet.payload,decoded.payload,n)==0);}
    uint32_t seed=0xC003U;for(unsigned int n=0;n<10000;++n){size_t size=n%VEL_FRAME;for(size_t i=0;i<size;++i){seed=seed*1664525U+1013904223U;bytes[i]=(uint8_t)(seed>>24);} (void)vel_decode(bytes,size,&decoded);}
    CHECK(vel_decode(NULL,1,&decoded)!=0);CHECK(vel_encode(NULL,bytes,sizeof bytes)==0);puts("C_CODEC_BOUNDS_CRC_FUZZ_PASS");return 0;
}
