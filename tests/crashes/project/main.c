#include <stdio.h>
#include "parser.h"

int main(void)
{
    const char *input = "name=segwhy;version=;lang=c";
    struct config cfg;

    parse_config(input, &cfg);
    printf("name: %s\n", cfg.name);
    return 0;
}
