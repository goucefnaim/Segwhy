#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    char *name = malloc(16);

    strcpy(name, "segwhy");
    free(name);
    printf("%c\n", name[0]);
    return 0;
}
