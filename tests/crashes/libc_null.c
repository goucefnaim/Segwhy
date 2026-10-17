#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    char *line = getenv("SEGWHY_SURELY_UNSET_VARIABLE");

    printf("length: %zu\n", strlen(line));
    return 0;
}
