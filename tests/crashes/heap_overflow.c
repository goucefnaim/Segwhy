#include <stdlib.h>

int main(void)
{
    int *tab = malloc(5 * sizeof(int));

    for (int i = 0; i <= 5; i++)
        tab[i] = i;
    free(tab);
    return 0;
}
