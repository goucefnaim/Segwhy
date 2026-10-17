#include <stdlib.h>

void cleanup(int *data)
{
    free(data);
}

int main(void)
{
    int *data = malloc(10 * sizeof(int));

    cleanup(data);
    free(data);
    return 0;
}
