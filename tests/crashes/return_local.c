#include <stdio.h>

int *make_counter(void)
{
    int counter = 0;

    return &counter;
}

int main(void)
{
    int *c = make_counter();

    *c += 1;
    printf("%d\n", *c);
    return 0;
}
