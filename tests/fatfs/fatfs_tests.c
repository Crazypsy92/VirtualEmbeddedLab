#define _POSIX_C_SOURCE 200809L
#include "ff.h"
#include "diskio.h"
#include "host_storage.h"
#include "vel_diskio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while (0)
#define FOK(x) do { FRESULT result_=(x); if (result_!=FR_OK) { fprintf(stderr,"FatFs result=%u\n",(unsigned int)result_); CHECK(result_==FR_OK); } } while (0)
#define BOK(x) CHECK((x)==BD_OK)
static host_storage storage;
static bd_device device;
static FATFS fs;
static bool created;
static unsigned char payload[32768], readback[32768];
static host_storage_config config;
static void attach(const char *root,bool fresh,bool ro)
{
    host_storage_init(&storage,&device);
    config=(host_storage_config){root,"sdcard.img",HOST_SD_SECTORS,fresh,ro};
    BOK(bd_open(&device,&config)); vel_disk_bind(&device); created=fresh;
}
static void detach(void)
{
    FOK(f_mount(NULL,"0:",0)); BOK(bd_sync(&device)); BOK(bd_close(&device)); vel_disk_bind(NULL);
}
static void mount_existing(void) { FOK(f_mount(&fs,"0:",1)); }
static void format_new(void)
{
    CHECK(created); /* Never exposed as a format-existing operation. */
    unsigned char work[4096];
    MKFS_PARM options={.fmt=FM_FAT|FM_SFD,.n_fat=2,.align=1,.n_root=512,.au_size=4096};
    FOK(f_mkfs("0:",&options,work,sizeof work)); created=false; mount_existing();
    CHECK(fs.fs_type==FS_FAT16 && fs.csize==8 && fs.volbase==0 && fs.n_fats==2);
    printf("VOLUME FAT16 SFD sector=512 clusters=%lu cluster_bytes=%lu fat_sectors=%lu fatbase=%lu database=%lu\n",(unsigned long)fs.n_fatent-2UL,(unsigned long)fs.csize*512UL,(unsigned long)fs.fsize,(unsigned long)fs.fatbase,(unsigned long)fs.database);
}
static unsigned char byte_at(uint32_t i) { return (unsigned char)((i*73U+(i>>7)+19U)&255U); }
static uint64_t hash(const unsigned char *b,size_t n)
{
    uint64_t h=UINT64_C(14695981039346656037);
    for (size_t i=0;i<n;++i) { h^=b[i]; h*=UINT64_C(1099511628211); } return h;
}
static void write_file(const char *path,const unsigned char *b,UINT size,BYTE flags)
{
    FIL file; UINT done=0; FOK(f_open(&file,path,flags)); FOK(f_write(&file,b,size,&done)); CHECK(done==size);
    FOK(f_sync(&file)); FOK(f_close(&file));
}
static void verify_file(const char *path,const unsigned char *b,UINT size)
{
    FIL file; FILINFO info; UINT done=0; FOK(f_stat(path,&info)); CHECK(info.fsize==size);
    FOK(f_open(&file,path,FA_READ)); CHECK(f_size(&file)==size);
    memset(readback,0xA7,sizeof readback); FOK(f_read(&file,readback,size+1U,&done)); CHECK(done==size && memcmp(readback,b,size)==0);
    CHECK(f_eof(&file)); FOK(f_close(&file));
    printf("CONTENT path=%s bytes=%u FNV1a64=%016" PRIx64 "\n",path,size,hash(readback,size));
}
static void file_io(void)
{
    DWORD free_before,free_after; FATFS *ptr; FOK(f_getfree("0:",&free_before,&ptr)); CHECK(ptr==&fs);
    write_file("0:/DATA.BIN",payload,24593,FA_CREATE_NEW|FA_WRITE);
    write_file("0:/DATA.BIN",payload+24593,121,FA_OPEN_APPEND|FA_WRITE);
    verify_file("0:/DATA.BIN",payload,24714);
    FIL file; UINT n; FOK(f_open(&file,"0:/DATA.BIN",FA_READ)); FOK(f_lseek(&file,4093));
    FOK(f_read(&file,readback,3001,&n)); CHECK(n==3001 && memcmp(readback,payload+4093,3001)==0); FOK(f_close(&file));
    write_file("0:/EMPTY.TXT",payload,0,FA_CREATE_NEW|FA_WRITE); verify_file("0:/EMPTY.TXT",payload,0);
    CHECK(f_open(&file,"0:/MISSING.TXT",FA_READ)==FR_NO_FILE);
    CHECK(f_open(&file,"0:/MISSING/A.TXT",FA_READ)==FR_NO_PATH);
    CHECK(f_open(&file,"0:/BAD?.TXT",FA_CREATE_NEW|FA_WRITE)==FR_INVALID_NAME);
    FILINFO info; FOK(f_stat("0:/DATA.BIN",&info)); CHECK(info.fdate==(WORD)(((2026-1980)<<9)|(1<<5)|1));
    FOK(f_getfree("0:",&free_after,&ptr)); CHECK(free_before-free_after==7U);
    printf("SPACE before=%lu after=%lu consumed_clusters=%lu\n",(unsigned long)free_before,(unsigned long)free_after,(unsigned long)(free_before-free_after));
}
static void directories(void)
{
    DWORD before,after; FATFS *ptr; FOK(f_getfree("0:",&before,&ptr));
    FOK(f_mkdir("0:/LOGS")); FOK(f_mkdir("0:/LOGS/SUB"));
    write_file("0:/LOGS/A.TXT",payload,7000,FA_CREATE_NEW|FA_WRITE);
    FOK(f_rename("0:/LOGS/A.TXT","0:/LOGS/SUB/B.TXT")); verify_file("0:/LOGS/SUB/B.TXT",payload,7000);
    DIR dir; FILINFO info; FOK(f_opendir(&dir,"0:/LOGS/SUB")); unsigned int count=0;
    for (;;) { FOK(f_readdir(&dir,&info)); if (info.fname[0]=='\0') { break; } CHECK(strcmp(info.fname,"B.TXT")==0 && info.fsize==7000); ++count; }
    CHECK(count==1); FOK(f_closedir(&dir));
    CHECK(f_unlink("0:/LOGS/SUB")==FR_DENIED);
    FOK(f_unlink("0:/LOGS/SUB/B.TXT")); CHECK(f_stat("0:/LOGS/SUB/B.TXT",&info)==FR_NO_FILE);
    FOK(f_unlink("0:/LOGS/SUB")); FOK(f_unlink("0:/LOGS")); CHECK(f_stat("0:/LOGS",&info)==FR_NO_FILE);
    FOK(f_getfree("0:",&after,&ptr)); CHECK(after==before);
}
static void diskio_tests(void)
{
    BYTE b[1024]; LBA_t sectors=0; WORD size=0; DWORD block=0;
    CHECK(disk_status(1)==STA_NOINIT && disk_initialize(0)==0);
    CHECK(disk_read(1,b,0,1)==RES_PARERR && disk_read(0,NULL,0,1)==RES_PARERR && disk_read(0,b,0,0)==RES_PARERR);
    CHECK(disk_read(0,b,65536,1)==RES_PARERR && disk_read(0,b,65535,2)==RES_PARERR);
    CHECK(disk_write(0,NULL,0,1)==RES_PARERR && disk_write(1,b,0,1)==RES_PARERR);
    CHECK(disk_ioctl(0,GET_SECTOR_COUNT,&sectors)==RES_OK && sectors==65536);
    CHECK(disk_ioctl(0,GET_SECTOR_SIZE,&size)==RES_OK && size==512);
    CHECK(disk_ioctl(0,GET_BLOCK_SIZE,&block)==RES_OK && block==1);
    CHECK(disk_ioctl(0,GET_SECTOR_COUNT,NULL)==RES_PARERR && disk_ioctl(1,CTRL_SYNC,NULL)==RES_PARERR);
    CHECK(disk_ioctl(0,255,&block)==RES_PARERR);
    host_fault_plan fault={.read_on=1}; host_storage_fault_reset(&storage,&fault);
    CHECK(disk_read(0,b,0,1)==RES_ERROR && storage.fault_hits==1);
    fault=(host_fault_plan){.sync_on=1}; host_storage_fault_reset(&storage,&fault);
    CHECK(disk_ioctl(0,CTRL_SYNC,NULL)==RES_ERROR && storage.fault_hits==1);
    host_storage_fault_reset(&storage,NULL); BOK(bd_close(&device));
    CHECK(disk_read(0,b,0,1)==RES_NOTRDY && disk_status(0)==STA_NOINIT);
    vel_disk_bind(NULL);
    CHECK(disk_read(0,b,0,1)==RES_NOTRDY && disk_write(0,b,0,1)==RES_NOTRDY && disk_ioctl(0,CTRL_SYNC,NULL)==RES_NOTRDY);
    vel_disk_bind(&device);
    config.create_new=false; BOK(bd_open(&device,&config));
}
static void recovery_observe(const char *path,UINT wanted)
{
    FOK(f_mount(NULL,"0:",0)); BOK(bd_sync(&device)); BOK(bd_close(&device));
    config.create_new=false; BOK(bd_open(&device,&config));
    FRESULT m=f_mount(&fs,"0:",1);
    printf("RECOVERY mount=%u ",(unsigned int)m);
    CHECK(m==FR_OK || m==FR_NO_FILESYSTEM || m==FR_DISK_ERR);
    if (m!=FR_OK) { puts("requires_repair=yes complete_content=no"); return; }
    FIL file; FRESULT r=f_open(&file,path,FA_READ);
    if (r==FR_OK) {
        UINT n=0; r=f_read(&file,readback,sizeof readback,&n);
        bool complete=r==FR_OK && n==wanted && memcmp(readback,payload,n)==0;
        printf("file_result=%u stored_bytes=%u complete_content=%s FNV1a64=%016" PRIx64 "\n",(unsigned int)r,n,complete?"yes":"no",hash(readback,n));
        FRESULT close_result=f_close(&file); CHECK(close_result==FR_OK || close_result==FR_DISK_ERR);
    } else { CHECK(r==FR_NO_FILE || r==FR_DISK_ERR || r==FR_INT_ERR); printf("file_result=%u complete_content=no\n",(unsigned int)r); }
}
static void io_fault(bool sync_fault)
{
    FIL file; UINT n; FOK(f_open(&file,"0:/FAIL.BIN",FA_CREATE_NEW|FA_WRITE)); FOK(f_sync(&file));
    host_fault_plan f=sync_fault ? (host_fault_plan){.sync_on=1} : (host_fault_plan){.write_on=1,.partial_blocks=1};
    host_storage_fault_reset(&storage,&f);
    FRESULT r=f_write(&file,payload,16384,&n);
    if (sync_fault) { FOK(r); CHECK(n==16384); r=f_sync(&file); }
    CHECK(r==FR_DISK_ERR && storage.fault_hits==1);
    printf("INJECTION kind=%s API_result=%u reported_bytes=%u hits=%llu partial_effects=possible\n",sync_fault?"sync":"write",(unsigned int)r,n,(unsigned long long)storage.fault_hits);
    host_storage_fault_reset(&storage,NULL); printf("close_after_error=%u\n",(unsigned int)f_close(&file));
    recovery_observe("0:/FAIL.BIN",16384);
}
static void corrupt_metadata(void)
{
    bd_transfer t; unsigned char original[512],bad[512]; FOK(f_mount(NULL,"0:",0));
    BOK(bd_read_blocks(&device,0,1,original,sizeof original,&t));
    for (unsigned int i=0;i<8;++i) {
        memcpy(bad,original,512);
        switch(i) {
        case 0: bad[13]=0; break;
        case 1: bad[13]=3; break;
        case 2: bad[16]=0; break;
        case 3: bad[11]=1; bad[12]=2; break;
        case 4: bad[14]=0; bad[15]=0; break;
        case 5: bad[22]=0; bad[23]=0; memset(bad+36,0xff,4); memcpy(bad+82,"FAT32   ",8); break;
        case 6: bad[22]=1; bad[23]=0; break;
        default: memset(bad,0,512); break;
        }
        BOK(bd_write_blocks(&device,0,1,bad,sizeof bad,&t)); BOK(bd_sync(&device));
        FRESULT r=f_mount(&fs,"0:",1); CHECK(r==FR_NO_FILESYSTEM);
        printf("CORRUPT targeted_case=%u mount=%u rejected=yes repair_required=yes\n",i,(unsigned int)r); FOK(f_mount(NULL,"0:",0));
    }
    uint32_t random=0xC0FFEEU;
    for (unsigned int i=0;i<64;++i) {
        for (size_t j=0;j<512;++j) { random=random*1664525U+1013904223U; bad[j]=(unsigned char)(random>>24); }
        BOK(bd_write_blocks(&device,0,1,bad,sizeof bad,&t)); FRESULT r=f_mount(&fs,"0:",1);
        CHECK(r==FR_NO_FILESYSTEM || r==FR_DISK_ERR); FOK(f_mount(NULL,"0:",0));
    }
    BOK(bd_write_blocks(&device,0,1,original,sizeof original,&t)); BOK(bd_sync(&device)); mount_existing();
    puts("CORPUS seed=0xC0FFEE cases=64 no_crash_no_oob; restored_original_mount=OK");
}
#define SLOTS 12U
#define LIMIT 8192U
typedef struct { bool active,alternate; UINT size; unsigned char bytes[LIMIT]; } model_file;
static model_file model[SLOTS];
static uint32_t random_state;
static uint32_t rng(void) { random_state^=random_state<<13; random_state^=random_state>>17; random_state^=random_state<<5; return random_state; }
static void filename(char *name,size_t size,unsigned int slot,bool alternate)
{
    int n=snprintf(name,size,"0:/S%02u%c.BIN",slot,alternate?'B':'A'); CHECK(n>0 && (size_t)n<size);
}
static void stress(bool io)
{
    memset(model,0,sizeof model); random_state=0x5EED1234U;
    for (unsigned int step=0;step<200;++step) {
        unsigned int op=rng()%4U,slot=rng()%SLOTS; model_file *m=&model[slot]; char name[32],next[32]; filename(name,sizeof name,slot,m->alternate);
        UINT n=(UINT)(rng()%6000U+1U); uint32_t salt=rng();
        printf("STRESS seed=0x5EED1234 op=%u kind=%u slot=%u n=%u live=%u\n",step,op,slot,n,m->active?1U:0U);
        if (op==0) {
            m->active=true; m->size=n;
            for (UINT j=0;j<n;++j) { m->bytes[j]=(unsigned char)((salt+j*37U)&255U); }
            if (io) { write_file(name,m->bytes,n,FA_CREATE_ALWAYS|FA_WRITE); }
        } else if (op==1 && m->active) {
            if (io) { FOK(f_unlink(name)); } m->active=false;
        } else if (op==2 && m->active) {
            filename(next,sizeof next,slot,!m->alternate);
            if (io) { FOK(f_rename(name,next)); } m->alternate=!m->alternate;
        } else if (op==3 && m->active) {
            n=n>LIMIT-m->size ? LIMIT-m->size : n;
            for (UINT j=0;j<n;++j) { m->bytes[m->size+j]=(unsigned char)((salt+j*53U)&255U); }
            if (io) { write_file(name,m->bytes+m->size,n,FA_OPEN_APPEND|FA_WRITE); } m->size+=n;
        }
    }
    for (unsigned int slot=0;slot<SLOTS;++slot) {
        model_file *m=&model[slot]; char name[32]; FILINFO info;
        filename(name,sizeof name,slot,m->alternate);
        if (m->active) { verify_file(name,m->bytes,m->size); } else { CHECK(f_stat(name,&info)==FR_NO_FILE); }
        filename(name,sizeof name,slot,!m->alternate); CHECK(f_stat(name,&info)==FR_NO_FILE);
    }
    puts("STRESS model_verified operations=200 seed=0x5EED1234");
}
int main(int argc,char **argv)
{
    CHECK(argc==3); const char *mode=argv[1]; for (uint32_t i=0;i<sizeof payload;++i) { payload[i]=byte_at(i); }
    bool existing=strcmp(mode,"cross-read")==0 || strcmp(mode,"cross-verify")==0 || strcmp(mode,"stress-read")==0 || strcmp(mode,"crash-write")==0 || strcmp(mode,"crash-observe")==0;
    attach(argv[2],!existing,false);
    if (strcmp(mode,"format")==0) { CHECK(f_mount(&fs,"0:",1)==FR_NO_FILESYSTEM); }
    if (existing) { mount_existing(); } else { format_new(); }
    if (strcmp(mode,"fileio")==0) { file_io(); }
    else if (strcmp(mode,"directory")==0) { directories(); }
    else if (strcmp(mode,"diskio")==0) { diskio_tests(); }
    else if (strcmp(mode,"remount")==0) {
        write_file("0:/DATA.BIN",payload,24593,FA_CREATE_NEW|FA_WRITE);
        FOK(f_mount(NULL,"0:",0)); mount_existing(); verify_file("0:/DATA.BIN",payload,24593);
    } else if (strcmp(mode,"cross-write")==0) {
        FOK(f_mkdir("0:/PERSIST")); write_file("0:/PERSIST/DATA.BIN",payload,24593,FA_CREATE_NEW|FA_WRITE);
    } else if (strcmp(mode,"cross-read")==0) {
        verify_file("0:/PERSIST/DATA.BIN",payload,24593);
        write_file("0:/PERSIST/DATA.BIN",payload+24593,121,FA_OPEN_APPEND|FA_WRITE);
    } else if (strcmp(mode,"cross-verify")==0) { verify_file("0:/PERSIST/DATA.BIN",payload,24714); }
    else if (strcmp(mode,"write-fault")==0 || strcmp(mode,"sync-fault")==0) { io_fault(strcmp(mode,"sync-fault")==0); }
    else if (strcmp(mode,"readonly")==0) {
        write_file("0:/DATA.BIN",payload,9000,FA_CREATE_NEW|FA_WRITE); detach(); attach(argv[2],false,true); mount_existing();
        CHECK((disk_status(0)&STA_PROTECT)!=0); FIL file; CHECK(f_open(&file,"0:/DATA.BIN",FA_WRITE)==FR_WRITE_PROTECTED);
        CHECK(disk_write(0,payload,0,1)==RES_WRPRT); verify_file("0:/DATA.BIN",payload,9000);
    } else if (strcmp(mode,"truncate")==0) {
        CHECK(ftruncate(storage.fd,512)==0); unsigned char b[512]; CHECK(disk_read(0,b,0,1)==RES_ERROR);
        FOK(f_mount(NULL,"0:",0)); CHECK(f_mount(&fs,"0:",1)==FR_NOT_READY); BOK(bd_close(&device));
        config.create_new=false; CHECK(bd_open(&device,&config)==BD_GEOMETRY); puts("TRUNCATION rejected geometry; no recovery claimed"); return 0;
    } else if (strcmp(mode,"corrupt")==0) { corrupt_metadata(); }
    else if (strcmp(mode,"stress-write")==0 || strcmp(mode,"stress-read")==0) { stress(strcmp(mode,"stress-write")==0); }
    else if (strcmp(mode,"crash-seed")==0) { write_file("0:/CRASH.BIN",payload,512,FA_CREATE_NEW|FA_WRITE); }
    else if (strcmp(mode,"crash-write")==0) {
        FIL file; UINT n; FOK(f_open(&file,"0:/CRASH.BIN",FA_OPEN_APPEND|FA_WRITE)); FOK(f_write(&file,payload+512,123,&n)); CHECK(n==123);
        /* No f_sync/f_close/bd_sync: only a partial sector is in the FatFs cache. */
        puts("CRASH_READY unsynced_bytes=123 old_committed=512"); CHECK(fflush(stdout)==0); for (;;) { (void)pause(); }
    } else if (strcmp(mode,"crash-observe")==0) {
        /* This specific kill point loses only cached bytes; it is not a general power-loss guarantee. */
        verify_file("0:/CRASH.BIN",payload,512); puts("RECOVERY mount=OK complete_new_content=no old_committed_content=yes lost_unsynced_bytes=123");
    } else { CHECK(strcmp(mode,"format")==0); }
    detach(); printf("FATFS PASS mode=%s pid=%ld\n",mode,(long)getpid()); return 0;
}
