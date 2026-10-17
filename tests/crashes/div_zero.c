#include <stdio.h>

int average(int total, int count)
{
    return total / count;
}

int main(void)
{
    printf("%d\n", average(100, 0));
    return 0;
}
