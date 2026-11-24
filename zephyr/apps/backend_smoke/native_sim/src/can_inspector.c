#include <errno.h>
#include <string.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>

#define COMMAND_SIZE 20
#define STANDARD_ONLY 1
#define EXTENDED_ONLY 2

CAN_MSGQ_DEFINE(standard_rx, 4);
CAN_MSGQ_DEFINE(extended_rx, 4);

static const struct device *const can = DEVICE_DT_GET(DT_NODELABEL(can_loopback0));
static const struct device *const control = DEVICE_DT_GET(DT_NODELABEL(uart1));
static int standard_filter = -1, extended_filter = -1;
static unsigned int active_filter = UINT8_MAX;

static int set_filters(unsigned int choice)
{
 if (active_filter == choice) {
  return 0;
 }
 if (standard_filter >= 0) {
  can_remove_rx_filter(can, standard_filter);
  standard_filter = -1;
 }
 if (extended_filter >= 0) {
  can_remove_rx_filter(can, extended_filter);
  extended_filter = -1;
 }
 const struct can_filter standard = {.id = 0, .mask = 0, .flags = 0};
 const struct can_filter extended = {.id = 0, .mask = 0, .flags = CAN_FILTER_IDE};
 if (choice != EXTENDED_ONLY) {
  standard_filter = can_add_rx_filter_msgq(can, &standard_rx, &standard);
  if (standard_filter < 0) {
   return standard_filter;
  }
 }
 if (choice != STANDARD_ONLY) {
  extended_filter = can_add_rx_filter_msgq(can, &extended_rx, &extended);
  if (extended_filter < 0) {
   return extended_filter;
  }
 }
 active_filter = choice;
 return 0;
}

static void frame_event(uint32_t sequence, const char *event, const struct can_frame *frame,
                        unsigned int queue)
{
 static const char hex[] = "0123456789abcdef";
 char data[CAN_MAX_DLEN * 2 + 1] = "-";

 for (size_t i = 0; i < frame->dlc; ++i) {
  data[2 * i] = hex[frame->data[i] >> 4];
  data[2 * i + 1] = hex[frame->data[i] & 15];
  data[2 * i + 2] = '\0';
 }
 printk("CAN_FRAME %u %s %lld %x %x %u %s %u\n", sequence, event,
        (long long)k_uptime_get(), frame->id, frame->flags, frame->dlc, data, queue);
}

static void dispatch(const uint8_t *data)
{
 const uint32_t sequence = sys_get_be32(&data[1]);
 const unsigned int extended = data[9];
 const unsigned int filter = data[11];
 struct can_frame tx = {.id = sys_get_be32(&data[5]), .dlc = data[10],
                        .flags = extended ? CAN_FRAME_IDE : 0};
 const uint32_t max_id = extended ? CAN_EXT_ID_MASK : CAN_STD_ID_MASK;

 if (sequence == 0 || extended > 1 || tx.id > max_id || tx.dlc > CAN_MAX_DLEN ||
     filter > EXTENDED_ONLY) {
  printk("CAN_DONE %u %d %u\n", sequence, -EINVAL, active_filter);
  return;
 }
 int rc = set_filters(filter);
 if (rc != 0) {
  printk("CAN_DONE %u %d %u\n", sequence, rc, active_filter);
  return;
 }
 memcpy(tx.data, &data[12], tx.dlc);
 frame_event(sequence, "TX", &tx, 0);
 rc = can_send(can, &tx, K_MSEC(100), NULL, NULL);
 if (rc == 0) {
  struct can_frame rx;
  struct k_msgq *expected = extended ? &extended_rx : &standard_rx;
  const unsigned int expected_queue = extended ? EXTENDED_ONLY : STANDARD_ONLY;

  if (k_msgq_get(expected, &rx, K_MSEC(25)) == 0) {
   frame_event(sequence, "RX", &rx, expected_queue);
  }
  while (k_msgq_get(&standard_rx, &rx, K_NO_WAIT) == 0) {
   frame_event(sequence, "RX", &rx, STANDARD_ONLY);
  }
  while (k_msgq_get(&extended_rx, &rx, K_NO_WAIT) == 0) {
   frame_event(sequence, "RX", &rx, EXTENDED_ONLY);
  }
 }
 printk("CAN_DONE %u %d %u\n", sequence, rc, active_filter);
}

int main(void)
{
 if (!device_is_ready(can) || !device_is_ready(control) ||
     can_set_mode(can, CAN_MODE_LOOPBACK) != 0 || can_start(can) != 0 || set_filters(0) != 0) {
  printk("CAN_INIT_FAILED\n");
  return 1;
 }
 printk("CAN_READY\n");
 uint8_t command[COMMAND_SIZE];
 size_t length = 0;

 while (true) {
  unsigned char byte;
  while (uart_poll_in(control, &byte) == 0) {
   if (length != 0 || byte == 'C') {
    command[length++] = byte;
    if (length == sizeof(command)) {
     dispatch(command);
     length = 0;
    }
   }
  }
  k_msleep(1);
 }
}
