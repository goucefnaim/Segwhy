#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    (void)argc;
    int n = atoi(argv[1]);

    printf("%d squared is %d\n", n, n * n);
    return 0;
}
