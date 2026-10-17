#include <stdio.h>

int grid[4];

int main(void)
{
    for (int i = 0; i < 10; i++)
        grid[i] = i;
    printf("%d\n", grid[0]);
    return 0;
}
