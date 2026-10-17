#include <stdio.h>

int main(void)
{
    char *greeting = "hello";

    greeting[0] = 'H';
    printf("%s\n", greeting);
    return 0;
}
