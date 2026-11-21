#ifndef VEL_WIRE_H
#define VEL_WIRE_H
#include <stdint.h>
#include <stddef.h>
#define VEL_PAYLOAD 64U
#define VEL_FRAME 82U
#define VEL_HELLO 1U
#define VEL_DATA 2U
#define VEL_START 3U
#define VEL_STOP 4U
#define VEL_RATE 5U
#define VEL_STATUS 6U
#define VEL_ACK 7U
#define VEL_NACK 8U
#define VEL_ERROR 9U
typedef struct { uint8_t type,id; uint32_t seq; uint16_t length; uint8_t payload[VEL_PAYLOAD]; } vel_packet;
uint32_t vel_crc(const uint8_t *,size_t);
void vel_put32(uint8_t *,uint32_t);
uint32_t vel_get32(const uint8_t *);
size_t vel_encode(const vel_packet *,uint8_t *,size_t);
int vel_decode(const uint8_t *,size_t,vel_packet *);
#endif
