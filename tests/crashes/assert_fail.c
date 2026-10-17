#include <assert.h>
#include <stdio.h>

int main(void)
{
    int balance = -5;

    assert(balance >= 0);
    printf("%d\n", balance);
    return 0;
}
