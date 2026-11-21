#include "checksum.h"
#include <stdio.h>
int main(void)
{
    const uint8_t data[] = {1, 2, 3, 255};
    if (vel_checksum(data, sizeof data) != 261U || vel_checksum(data, 0) != 0U) { return 1; }
    puts("[HOST] checksum and empty-input tests PASS");
    return 0;
}
