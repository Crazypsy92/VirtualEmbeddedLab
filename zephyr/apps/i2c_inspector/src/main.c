/* Bridge the native Zephyr controller to the lab's shared device model. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/i2c_emul.h>

#define MAX_READ 32
#define MAX_WRITE (MAX_READ + 1)

static const struct device *const bus = DEVICE_DT_GET(DT_NODELABEL(i2c0));

static int unhex(char ch)
{
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    return -1;
}

static int read_hex(const char *s, uint8_t *buf, size_t capacity)
{
    size_t len = strlen(s);
    if (strcmp(s, "-") == 0) {
        return 0;
    }
    if (len % 2 || len / 2 > capacity) {
        return -EINVAL;
    }
    for (size_t i = 0; i < len / 2; ++i) {
        int high = unhex(s[2 * i]);
        int low = unhex(s[2 * i + 1]);
        if (high < 0 || low < 0) {
            return -EINVAL;
        }
        buf[i] = (uint8_t)((high << 4) | low);
    }
    return (int)(len / 2);
}

static void print_hex(const uint8_t *data, size_t size)
{
    if (!size) {
        putchar('-');
    }
    for (size_t i = 0; i < size; ++i) {
        printf("%02x", data[i]);
    }
    putchar('\n');
    fflush(stdout);
}

static int emulate(const struct emul *target, struct i2c_msg *msgs, int count, int address)
{
    (void)target;
    if (count < 1 || count > 2) {
        return -EINVAL;
    }
    struct i2c_msg *write = &msgs[0];
    struct i2c_msg *read = &msgs[count - 1];
    bool has_write = !(write->flags & I2C_MSG_READ);
    bool has_read = (read->flags & I2C_MSG_READ) != 0;

    printf("CALL %d %d %u %u %u ", address, count, msgs[0].flags,
           count > 1 ? msgs[1].flags : 0, has_read ? read->len : 0);
    print_hex(write->buf, has_write ? write->len : 0);
    char line[96], hex[67];
    int rc;
    if (!fgets(line, sizeof(line), stdin) || sscanf(line, "%d %66s", &rc, hex) != 2) {
        return -EIO;
    }
    if (rc != 0) {
        return rc;
    }
    return read_hex(hex, read->buf, has_read ? read->len : 0) == (int)(has_read ? read->len : 0)
           ? 0 : -EIO;
}

static const struct emul target = {.dev = DEVICE_DT_GET(DT_NODELABEL(i2c0))};
static const struct i2c_emul_api api = {.transfer = emulate};
static struct i2c_emul devices[] = {{.target = &target, .api = &api},
                                    {.target = &target, .api = &api}};

int main(void)
{
    char line[128], hex[67];
    unsigned int khz, addr, size, first, second;
    if (!device_is_ready(bus) || !fgets(line, sizeof(line), stdin) ||
        sscanf(line, "INIT %u %u", &first, &second) != 2 ||
        first < 8 || first > 119 || second < 8 || second > 119 || first == second) {
        return 1;
    }
    devices[0].addr = first;
    devices[1].addr = second;
    for (size_t i = 0; i < ARRAY_SIZE(devices); ++i) {
        if (i2c_emul_register(bus, &devices[i]) != 0) {
            return 1;
        }
    }
    puts("READY");
    fflush(stdout);
    while (fgets(line, sizeof(line), stdin)) {
        uint8_t tx[MAX_WRITE], rx[MAX_READ];
        if (sscanf(line, "GO %u %u %u %66s", &khz, &addr, &size, hex) != 4 ||
            (khz != 100 && khz != 400) || addr < 8 || addr > 119 || size > MAX_READ) {
            return 2;
        }
        int len = read_hex(hex, tx, sizeof(tx));
        if (len < 0) {
            return 2;
        }
        uint32_t mode = I2C_MODE_CONTROLLER |
                        I2C_SPEED_SET(khz == 100 ? I2C_SPEED_STANDARD : I2C_SPEED_FAST);
        struct i2c_msg msgs[2] = {{0}};
        uint8_t count = 0;
        if (len || !size) {
            msgs[count++] = (struct i2c_msg){tx, (uint32_t)len, size ? 0 : I2C_MSG_STOP};
        }
        if (size) {
            msgs[count++] = (struct i2c_msg){rx, size, I2C_MSG_READ | I2C_MSG_STOP |
                                                      (len ? I2C_MSG_RESTART : 0)};
        }
        uint32_t cfg = 0;
        int rc = i2c_configure(bus, mode);
        if (!rc) {
            rc = i2c_get_config(bus, &cfg);
        }
        if (!rc) {
            rc = i2c_transfer(bus, msgs, count, addr);
        }
        printf("DONE %d %u ", rc, I2C_SPEED_GET(cfg));
        print_hex(rx, rc == 0 ? size : 0);
    }
    return 0;
}
