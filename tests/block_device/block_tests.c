#define _POSIX_C_SOURCE 200809L
#include "host_storage.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while (0)
#define OK(x) CHECK((x)==BD_OK)
static unsigned char data[2048], back[2048];
static void pattern(void) { for (size_t i=0;i<sizeof data;++i) { data[i]=(unsigned char)((i*73U+19U)&255U); } }
int main(int argc,char **argv)
{
    CHECK(argc==3); const char *mode=argv[1], *root=argv[2]; pattern();
    host_storage s; bd_device d; host_storage_init(&s,&d);
    host_storage_config c={root,"sdcard.img",HOST_SD_SECTORS,true,false};
    bd_transfer t; bd_geometry g;
    if (strcmp(mode,"persist-read")==0) { c.create_new=false; }
    OK(bd_open(&d,&c));
    if (strcmp(mode,"basic")==0 || strcmp(mode,"persist-write")==0 || strcmp(mode,"persist-read")==0) {
        OK(bd_get_geometry(&d,&g)); CHECK(g.sector_count==65536 && g.sector_size==512);
        if (strcmp(mode,"persist-read")!=0) {
            OK(bd_write_blocks(&d,7,1,data,512,&t)); CHECK(t.blocks_completed==1);
            OK(bd_write_blocks(&d,100,4,data,sizeof data,&t)); CHECK(t.bytes_completed==2048);
            OK(bd_sync(&d));
        }
        OK(bd_read_blocks(&d,7,1,back,512,&t)); CHECK(memcmp(data,back,512)==0);
        OK(bd_read_blocks(&d,100,4,back,sizeof back,&t)); CHECK(memcmp(data,back,sizeof data)==0);
        if (strcmp(mode,"basic")==0) {
            OK(bd_close(&d)); c.create_new=false; c.read_only=true; OK(bd_open(&d,&c));
            CHECK(bd_write_blocks(&d,0,1,data,512,&t)==BD_READ_ONLY);
            bd_media_status m; OK(bd_get_status(&d,&m)); CHECK(m.open && m.read_only);
            OK(bd_read_blocks(&d,100,4,back,sizeof back,&t)); CHECK(memcmp(data,back,sizeof data)==0);
        }
    } else if (strcmp(mode,"geometry")==0) {
        CHECK(bd_read_blocks(&d,0,0,back,sizeof back,&t)==BD_INVALID);
        CHECK(bd_read_blocks(&d,65536,1,back,sizeof back,&t)==BD_RANGE);
        CHECK(bd_read_blocks(&d,65535,2,back,sizeof back,&t)==BD_RANGE);
        CHECK(bd_read_blocks(&d,UINT64_MAX,UINT32_MAX,back,sizeof back,&t)==BD_RANGE);
        CHECK(bd_read_blocks(&d,1,UINT32_MAX,back,sizeof back,&t)==BD_RANGE);
        CHECK(bd_read_blocks(&d,0,1,back,511,&t)==BD_INVALID);
        CHECK(bd_read_blocks(&d,0,1,NULL,512,&t)==BD_INVALID);
        CHECK(bd_write_blocks(NULL,0,1,data,512,&t)==BD_INVALID);
        CHECK(bd_read_blocks(&d,0,1,back,512,NULL)==BD_INVALID);
        OK(bd_write_blocks(&d,65535,1,data,512,&t));
        OK(bd_close(&d)); CHECK(bd_read_blocks(&d,0,1,back,512,&t)==BD_CLOSED);
        CHECK(bd_write_blocks(&d,0,1,data,512,&t)==BD_CLOSED); CHECK(bd_close(&d)==BD_CLOSED);
        CHECK(bd_sync(&d)==BD_CLOSED); CHECK(bd_get_geometry(&d,&g)==BD_CLOSED);
        c.sectors=UINT64_MAX; c.create_new=false; CHECK(bd_open(&d,&c)==BD_INVALID);
        c.sectors=65535; CHECK(bd_open(&d,&c)==BD_GEOMETRY); return 0;
    } else if (strcmp(mode,"faults")==0) {
        host_fault_plan f={.write_on=2,.partial_blocks=2}; host_storage_fault_reset(&s,&f);
        OK(bd_write_blocks(&d,20,4,back,sizeof back,&t));
        CHECK(bd_write_blocks(&d,20,4,data,sizeof data,&t)==BD_IO);
        CHECK(t.blocks_completed==2 && t.bytes_completed==1024 && s.fault_hits==1);
        printf("FAULT partial-write hits=%llu committed_blocks=%u bytes=%llu\n",(unsigned long long)s.fault_hits,t.blocks_completed,(unsigned long long)t.bytes_completed);
        host_storage_fault_reset(&s,NULL); OK(bd_read_blocks(&d,20,4,back,sizeof back,&t));
        CHECK(memcmp(data,back,1024)==0); for (size_t i=1024;i<2048;++i) { CHECK(back[i]==0); }
        f=(host_fault_plan){.read_on=1,.partial_blocks=1}; host_storage_fault_reset(&s,&f);
        CHECK(bd_read_blocks(&d,20,4,back,sizeof back,&t)==BD_IO && t.blocks_completed==1 && s.fault_hits==1);
        f=(host_fault_plan){.sync_on=2}; host_storage_fault_reset(&s,&f);
        OK(bd_sync(&d)); CHECK(bd_sync(&d)==BD_IO && s.fault_hits==1);
        f=(host_fault_plan){.write_on=1,.short_io=true}; host_storage_fault_reset(&s,&f);
        CHECK(bd_write_blocks(&d,30,1,data,512,&t)==BD_SHORT_IO && t.bytes_completed==511 && t.blocks_completed==0);
        f=(host_fault_plan){.read_on=1,.short_io=true}; host_storage_fault_reset(&s,&f);
        CHECK(bd_read_blocks(&d,30,1,back,512,&t)==BD_SHORT_IO && t.bytes_completed==511);
        CHECK(memcmp(data,back,511)==0);
        printf("FAULT short-read/write committed_bytes=511 hits=%llu\n",(unsigned long long)s.fault_hits);
        host_storage_fault_reset(&s,NULL); OK(bd_sync(&d)); CHECK(s.fault_hits==0);
        CHECK(ftruncate(s.fd,512)==0); CHECK(bd_read_blocks(&d,0,1,back,512,&t)==BD_GEOMETRY);
    } else if (strcmp(mode,"safety")==0) {
        OK(bd_write_blocks(&d,0,1,data,512,&t)); OK(bd_sync(&d)); OK(bd_close(&d));
        CHECK(bd_open(&d,&c)==BD_EXISTS);
        c.create_new=false; OK(bd_open(&d,&c));
        host_storage other; bd_device second; host_storage_init(&other,&second); CHECK(bd_open(&second,&c)==BD_BUSY);
        OK(bd_read_blocks(&d,0,1,back,512,&t)); CHECK(memcmp(data,back,512)==0); OK(bd_close(&d));
        c.name="../outside.img"; CHECK(bd_open(&d,&c)==BD_UNSAFE);
        char path[4096]; CHECK(snprintf(path,sizeof path,"%s/link.img",root)>0);
        const char *outside=getenv("VEL_SAFETY_OUTSIDE"); CHECK(outside!=NULL);
        CHECK(symlink(outside,path)==0); c.name="link.img"; CHECK(bd_open(&d,&c)==BD_UNSAFE);
        CHECK(snprintf(path,sizeof path,"%s/rootlink",root)>0); CHECK(symlink(root,path)==0);
        c.name="sdcard.img"; c.root=path; CHECK(bd_open(&d,&c)==BD_UNSAFE); c.root=root;
        char target[4096]; CHECK(snprintf(target,sizeof target,"%s/sdcard.img",root)>0);
        CHECK(snprintf(path,sizeof path,"%s/hard.img",root)>0); CHECK(link(target,path)==0);
        c.name="hard.img"; CHECK(bd_open(&d,&c)==BD_UNSAFE);
        return 0;
    } else { CHECK(0); }
    OK(bd_close(&d)); printf("BLOCK PASS mode=%s pid=%ld fault_hits=%llu\n",mode,(long)getpid(),(unsigned long long)s.fault_hits); return 0;
}
