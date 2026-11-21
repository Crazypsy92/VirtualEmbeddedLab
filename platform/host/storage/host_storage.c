#define _POSIX_C_SOURCE 200809L
#include "host_storage.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
static int safe_root(const char *path)
{
    if (path == NULL || path[0] != '/' || strlen(path) >= 4096U) { errno=EINVAL; return -1; }
    char copy[4096]; (void)strcpy(copy,path);
    int fd=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if (fd < 0) { return -1; }
    char *save=NULL;
    for (char *part=strtok_r(copy,"/",&save); part != NULL; part=strtok_r(NULL,"/",&save)) {
        if (strcmp(part,".")==0 || strcmp(part,"..")==0) { (void)close(fd); errno=EINVAL; return -1; }
        int next=openat(fd,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        (void)close(fd); if (next<0) { return -1; } fd=next;
    }
    return fd;
}
static bd_status geometry_check(host_storage *s)
{
    struct stat st;
    if (fstat(s->fd,&st)!=0) { return BD_IO; }
    if (!S_ISREG(st.st_mode) || st.st_nlink != 1) { return BD_UNSAFE; }
    return st.st_size >= 0 && (uint64_t)st.st_size == s->sectors*512U ? BD_OK : BD_GEOMETRY;
}
static bd_status storage_open(void *ctx,const void *cfg)
{
    host_storage *s=ctx; const host_storage_config *c=cfg;
    if (s->opened) { return BD_BUSY; }
    if (c->name==NULL || c->name[0]=='\0' || strchr(c->name,'/')!=NULL || strcmp(c->name,".")==0 || strcmp(c->name,"..")==0) { return BD_UNSAFE; }
    if (c->sectors==0 || c->sectors > (uint64_t)INT64_MAX/512U || (c->read_only && c->create_new)) { return BD_INVALID; }
    int root=safe_root(c->root);
    if (root<0) { return BD_UNSAFE; }
    int flags=(c->read_only ? O_RDONLY : O_RDWR)|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK;
    if (c->create_new) { flags|=O_CREAT|O_EXCL; }
    int fd=openat(root,c->name,flags,0600); int saved=errno; (void)close(root);
    if (fd<0) { return saved==EEXIST ? BD_EXISTS : saved==ELOOP ? BD_UNSAFE : BD_IO; }
    struct stat st;
    if (fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) || st.st_nlink!=1) { (void)close(fd); return BD_UNSAFE; }
    if (flock(fd,(c->read_only ? LOCK_SH : LOCK_EX)|LOCK_NB)!=0) { (void)close(fd); return BD_BUSY; }
    if (c->create_new && ftruncate(fd,(off_t)(c->sectors*512U))!=0) { (void)close(fd); return BD_IO; }
    s->fd=fd; s->sectors=c->sectors; s->read_only=c->read_only;
    bd_status result=geometry_check(s);
    if (result!=BD_OK) { (void)close(fd); s->fd=-1; return result; }
    s->opened=true; return BD_OK;
}
static bd_status storage_close(void *ctx)
{
    host_storage *s=ctx; if (!s->opened) { return BD_CLOSED; }
    int rc=close(s->fd); s->opened=false; s->fd=-1; return rc==0 ? BD_OK : BD_IO;
}
static bd_status check_request(host_storage *s,uint64_t l,uint32_t n,size_t size)
{
    if (!s->opened) { return BD_CLOSED; }
    if (n==0) { return BD_INVALID; }
    if (l>=s->sectors || (uint64_t)n>s->sectors-l) { return BD_RANGE; }
    if ((uint64_t)n*512U>SIZE_MAX || size<(uint64_t)n*512U) { return BD_INVALID; }
    return geometry_check(s);
}
static bd_status transfer(host_storage *s,uint64_t l,uint32_t n,void *buffer,size_t size,bd_transfer *t,bool write_op)
{
    bd_status rc=check_request(s,l,n,size); if (rc!=BD_OK) { return rc; }
    if (write_op && s->read_only) { return BD_READ_ONLY; }
    uint64_t call=write_op ? ++s->write_calls : ++s->read_calls;
    uint64_t trigger=write_op ? s->fault.write_on : s->fault.read_on;
    bool fault=trigger!=0 && call==trigger;
    uint32_t limit=n;
    if (fault) { ++s->fault_hits; limit=s->fault.partial_blocks<n ? s->fault.partial_blocks : n-1U; }
    for (uint32_t i=0;i<n;++i) {
        if (fault && i==limit && !s->fault.short_io) { return BD_IO; }
        size_t amount=fault && i==limit ? 511U : 512U;
        off_t offset=(off_t)((l+i)*512U);
        unsigned char *b=(unsigned char *)buffer+(size_t)i*512U;
        ssize_t done;
        do { done=write_op ? pwrite(s->fd,b,amount,offset) : pread(s->fd,b,amount,offset); } while (done<0 && errno==EINTR);
        if (done<0) { return BD_IO; }
        t->bytes_completed+=(uint64_t)done;
        if (done!=512) { return BD_SHORT_IO; }
        ++t->blocks_completed;
    }
    return BD_OK;
}
static bd_status storage_read(void *c,uint64_t l,uint32_t n,void *b,size_t z,bd_transfer *t) { return transfer(c,l,n,b,z,t,false); }
static bd_status storage_write(void *c,uint64_t l,uint32_t n,const void *b,size_t z,bd_transfer *t) { return transfer(c,l,n,(void *)b,z,t,true); }
static bd_status storage_sync(void *ctx)
{
    host_storage *s=ctx; if (!s->opened) { return BD_CLOSED; }
    bd_status rc=geometry_check(s); if (rc!=BD_OK) { return rc; }
    if (++s->sync_calls==s->fault.sync_on && s->fault.sync_on!=0) { ++s->fault_hits; return BD_IO; }
    int result; do { result=fsync(s->fd); } while (result<0 && errno==EINTR);
    return result==0 ? BD_OK : BD_IO;
}
static bd_status storage_geometry(void *ctx,bd_geometry *g)
{
    host_storage *s=ctx; if (!s->opened) { return BD_CLOSED; }
    bd_status rc=geometry_check(s); if (rc==BD_OK) { g->sector_count=s->sectors; g->sector_size=512; } return rc;
}
static bd_status storage_status(void *ctx,bd_media_status *m)
{
    host_storage *s=ctx; m->open=s->opened; m->read_only=s->read_only; return BD_OK;
}
static const bd_ops ops={storage_open,storage_close,storage_read,storage_write,storage_sync,storage_geometry,storage_status};
void host_storage_init(host_storage *s,bd_device *d) { memset(s,0,sizeof *s); s->fd=-1; d->ops=&ops; d->context=s; }
void host_storage_fault_reset(host_storage *s,const host_fault_plan *f)
{
    memset(&s->fault,0,sizeof s->fault); if (f!=NULL) { s->fault=*f; }
    s->read_calls=0; s->write_calls=0; s->sync_calls=0; s->fault_hits=0;
}
