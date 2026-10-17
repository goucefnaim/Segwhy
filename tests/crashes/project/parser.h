#ifndef PARSER_H
#define PARSER_H

struct config {
    char name[32];
    char version[32];
};

void parse_config(const char *input, struct config *cfg);

#endif
