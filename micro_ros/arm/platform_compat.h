/* Zephyr 4.4.2 posix/unistd.h omits isatty; Newlib libc-hooks.c exports it. */
#ifndef VEL_UROS_PLATFORM_COMPAT_H
#define VEL_UROS_PLATFORM_COMPAT_H
#ifdef __cplusplus
extern "C" {
#endif
#include <strings.h>
int isatty(int fd);
#ifdef __cplusplus
}
#endif
#endif
