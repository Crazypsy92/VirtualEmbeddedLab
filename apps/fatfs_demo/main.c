#include "ff.h"
#include "host_storage.h"
#include "vel_diskio.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv)
{
    if (argc!=3 || (strcmp(argv[1],"--create-new-and-format")!=0 && strcmp(argv[1],"--read-only")!=0)) {
        fprintf(stderr,"Usage: %s --create-new-and-format|--read-only /absolute/existing/test-directory\nOnly sdcard.img beneath that directory is used. Existing images are never formatted.\n",argv[0]); return 2;
    }
    bool fresh=strcmp(argv[1],"--create-new-and-format")==0;
    host_storage s; bd_device d; host_storage_init(&s,&d);
    host_storage_config c={argv[2],"sdcard.img",HOST_SD_SECTORS,fresh,!fresh};
    bd_status br=bd_open(&d,&c); if (br!=BD_OK) { fprintf(stderr,"open: %s\n",bd_status_name(br)); return 1; }
    vel_disk_bind(&d); FATFS fs; FIL f; FRESULT r=FR_OK; UINT n=0;
    if (fresh) {
        unsigned char work[4096]; MKFS_PARM options={.fmt=FM_FAT|FM_SFD,.n_fat=2,.align=1,.n_root=512,.au_size=4096};
        r=f_mkfs("0:",&options,work,sizeof work);
    }
    if (r==FR_OK) { r=f_mount(&fs,"0:",1); }
    const char message[]="VirtualEmbeddedLab FatFs R0.16 patch-2\n";
    if (r==FR_OK && fresh) {
        r=f_open(&f,"0:/HELLO.TXT",FA_CREATE_NEW|FA_WRITE);
        if (r==FR_OK) {
            r=f_write(&f,message,sizeof message-1U,&n);
            if (r==FR_OK && n!=sizeof message-1U) { r=FR_DISK_ERR; }
            if (r==FR_OK) { r=f_sync(&f); }
            FRESULT close_result=f_close(&f); if (r==FR_OK) { r=close_result; }
        }
    }
    if (r==FR_OK) {
        r=f_open(&f,"0:/HELLO.TXT",FA_READ);
        if (r==FR_OK) {
            char data[128]={0}; r=f_read(&f,data,sizeof data-1U,&n);
            if (r==FR_OK && (n!=sizeof message-1U || memcmp(data,message,n)!=0)) { r=FR_INT_ERR; }
            if (r==FR_OK) { printf("FAT type=%u cluster_bytes=%lu file_bytes=%u content=%s",fs.fs_type,(unsigned long)fs.csize*512UL,n,data); }
            FRESULT close_result=f_close(&f); if (r==FR_OK) { r=close_result; }
        }
    }
    (void)f_mount(NULL,"0:",0); bd_status sync=bd_sync(&d), close=bd_close(&d); vel_disk_bind(NULL);
    printf("FatFs result=%u sync=%s close=%s\n",(unsigned int)r,bd_status_name(sync),bd_status_name(close));
    return r==FR_OK && sync==BD_OK && close==BD_OK ? 0 : 1;
}
