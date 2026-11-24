/* Record positive syscalls on native_sim PTY masters without transforming bytes. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <execinfo.h>
#include <string.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static int trace_fd = -1;
static ssize_t (*real_read)(int, void *, size_t);
static ssize_t (*real_write)(int, const void *, size_t);

__attribute__((constructor)) static void open_trace(void)
{
    real_read = dlsym(RTLD_NEXT, "read");
    real_write = dlsym(RTLD_NEXT, "write");
    const char *path = getenv("VEL_PTY_TRACE");
    if (path) {
        trace_fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
        if (trace_fd < 0) _exit(78);
    }
}

static void record(int fd, const void *data, ssize_t count, size_t requested, const char *direction)
{
    int saved_errno = errno;
    unsigned int pty;
    if (trace_fd >= 0 && count > 0 && ioctl(fd, TIOCGPTN, &pty) == 0) {
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        char line[768];
        const unsigned char *bytes = data;
        const char digits[] = "0123456789abcdef";
        int n = snprintf(line, sizeof line,
            "{\"ns\":%lld,\"pty\":%u,\"dir\":\"%s\",\"bytes\":%zd,\"requested\":%zu,\"hex\":\"",
            (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec, pty, direction, count, requested);
        for (ssize_t i = 0; i < count && i < 256; i++) {
            line[n++] = digits[bytes[i] >> 4];
            line[n++] = digits[bytes[i] & 15U];
        }
        n += snprintf(line + n, sizeof line - (size_t)n, "\"");
        if (count == 8 && !strcmp(direction, "rx")) {
            void *frames[13];
            int depth = backtrace(frames, 13);
            n += snprintf(line + n, sizeof line - (size_t)n, ",\"stack\":[");
            for (int i = 0; i < depth; ++i) {
                n += snprintf(line + n, sizeof line - (size_t)n, "%s\"%p\"", i ? "," : "", frames[i]);
            }
            line[n++] = ']';
        }
        n += snprintf(line + n, sizeof line - (size_t)n, "}\n");
        (void)syscall(SYS_write, trace_fd, line, (size_t)n);
    }
    errno = saved_errno;
}

ssize_t read(int fd, void *buf, size_t len)
{
    ssize_t rc = real_read ? real_read(fd, buf, len) : syscall(SYS_read, fd, buf, len);
    record(fd, buf, rc, len, "rx");
    return rc;
}

ssize_t write(int fd, const void *buf, size_t len)
{
    ssize_t rc = real_write ? real_write(fd, buf, len) : syscall(SYS_write, fd, buf, len);
    record(fd, buf, rc, len, "tx");
    return rc;
}
