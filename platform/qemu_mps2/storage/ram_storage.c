#include "ram_storage.h"
#include <string.h>
void (*ram_io_hook)(void);
bool (*ram_fault_filter)(void);
unsigned char ram_bytes[RAM_BYTES] __attribute__((section(".ramdisk"),aligned(512)));
static bd_status ropen(void *ctx,const void *cfg)
{
    ram_storage *r=ctx; const ram_config *c=cfg;
    if (r->opened) { return BD_BUSY; } r->read_only=c->read_only;
    if (c->clear) { memset(ram_bytes,0,sizeof ram_bytes); } r->opened=true; return BD_OK;
}
static bd_status rclose(void *ctx) { ram_storage *r=ctx; if (!r->opened) { return BD_CLOSED; } r->opened=false; return BD_OK; }
static bd_status io(void *ctx,uint64_t l,uint32_t n,void *b,size_t z,bd_transfer *t,bool wr)
{
    ram_storage *r=ctx;
    if (!r->opened) { return BD_CLOSED; }
    if (!n || (uint64_t)n*512U>SIZE_MAX || z<(uint64_t)n*512U) { return BD_INVALID; }
    if (l>=RAM_SECTORS || n>RAM_SECTORS-l) { return BD_RANGE; }
    if (wr && r->read_only) { return BD_READ_ONLY; }
    bool eligible=ram_fault_filter==NULL || ram_fault_filter();
    bool fail=eligible && (wr ? ++r->write_calls==r->write_on && r->write_on!=0 : ++r->read_calls==r->read_on && r->read_on!=0);
    uint32_t limit=fail ? (r->partial<n ? r->partial : n-1U) : n;
    for (uint32_t i=0;i<limit;++i) {
        void *media=ram_bytes+(size_t)(l+i)*512U; unsigned char *memory=(unsigned char *)b+(size_t)i*512U;
        if (wr) { memcpy(media,memory,512); } else { memcpy(memory,media,512); }
        ++t->blocks_completed; t->bytes_completed+=512U;
        if (ram_io_hook!=NULL) { ram_io_hook(); }
    }
    r->last=*t;
    if (fail) { ++r->hits; return BD_IO; } return BD_OK;
}
static bd_status rread(void *c,uint64_t l,uint32_t n,void *b,size_t z,bd_transfer *t) { return io(c,l,n,b,z,t,false); }
static bd_status rwrite(void *c,uint64_t l,uint32_t n,const void *b,size_t z,bd_transfer *t) { return io(c,l,n,(void *)b,z,t,true); }
static bd_status rsync(void *c) { return ((ram_storage *)c)->opened ? BD_OK : BD_CLOSED; }
static bd_status rgeometry(void *c,bd_geometry *g) { if (!((ram_storage *)c)->opened) { return BD_CLOSED; } g->sector_count=RAM_SECTORS; g->sector_size=512; return BD_OK; }
static bd_status rstatus(void *c,bd_media_status *s) { s->open=((ram_storage *)c)->opened; s->read_only=((ram_storage *)c)->read_only; return BD_OK; }
static const bd_ops ops={ropen,rclose,rread,rwrite,rsync,rgeometry,rstatus};
void ram_storage_init(ram_storage *r,bd_device *d) { memset(r,0,sizeof *r); d->context=r; d->ops=&ops; }
void ram_fault(ram_storage *r,uint32_t read,uint32_t write,uint32_t partial) { r->read_on=read; r->write_on=write; r->partial=partial; r->read_calls=0; r->write_calls=0; r->hits=0; }
