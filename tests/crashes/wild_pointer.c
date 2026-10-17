#include <stdio.h>
#include <stdint.h>

int main(void)
{
    uintptr_t address = 0xdeadbeef;
    int *p = (int *)address;

    *p = 42;
    printf("%d\n", *p);
    return 0;
}
