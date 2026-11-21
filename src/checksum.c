#include "checksum.h"
uint32_t vel_checksum(const uint8_t *data, size_t size)
{
    uint32_t sum = 0;
    for (size_t i = 0; i < size; ++i) { sum += data[i]; }
    return sum;
}
