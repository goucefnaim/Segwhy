#include <stdio.h>
#include <stdlib.h>

struct node {
    int value;
    struct node *next;
};

int get_value(struct node *n)
{
    return n->value;
}

int main(void)
{
    struct node *head = NULL;

    printf("value: %d\n", get_value(head));
    return 0;
}
