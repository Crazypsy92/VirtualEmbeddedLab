#include "block_device/block_device.h"
#define VALID(d, member) ((d) != NULL && (d)->context != NULL && (d)->ops != NULL && (d)->ops->member != NULL)
bd_status bd_open(bd_device *d, const void *c) { return VALID(d,open) && c != NULL ? d->ops->open(d->context,c) : BD_INVALID; }
bd_status bd_close(bd_device *d) { return VALID(d,close) ? d->ops->close(d->context) : BD_INVALID; }
bd_status bd_sync(bd_device *d) { return VALID(d,sync) ? d->ops->sync(d->context) : BD_INVALID; }
bd_status bd_get_geometry(bd_device *d, bd_geometry *g) { return VALID(d,geometry) && g != NULL ? d->ops->geometry(d->context,g) : BD_INVALID; }
bd_status bd_get_status(bd_device *d, bd_media_status *s) { return VALID(d,status) && s != NULL ? d->ops->status(d->context,s) : BD_INVALID; }
bd_status bd_read_blocks(bd_device *d, uint64_t l, uint32_t n, void *b, size_t z, bd_transfer *t)
{
    if (t != NULL) { t->bytes_completed=0; t->blocks_completed=0; }
    return VALID(d,read) && b != NULL && t != NULL ? d->ops->read(d->context,l,n,b,z,t) : BD_INVALID;
}
bd_status bd_write_blocks(bd_device *d, uint64_t l, uint32_t n, const void *b, size_t z, bd_transfer *t)
{
    if (t != NULL) { t->bytes_completed=0; t->blocks_completed=0; }
    return VALID(d,write) && b != NULL && t != NULL ? d->ops->write(d->context,l,n,b,z,t) : BD_INVALID;
}
const char *bd_status_name(bd_status s)
{
    static const char *const names[]={"OK","INVALID","CLOSED","RANGE","READ_ONLY","IO","SHORT_IO","GEOMETRY","EXISTS","UNSAFE","BUSY"};
    return (unsigned int)s < sizeof names/sizeof names[0] ? names[s] : "UNKNOWN";
}
