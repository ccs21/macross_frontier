#pragma once
#include <stddef.h>
void *malloc(size_t);void free(void*);void abort(void);void exit(int);char *getenv(const char*);int atoi(const char*);unsigned long strtoul(const char*,char**,int);
void *_aligned_malloc(size_t,size_t);void _aligned_free(void*);
unsigned long _byteswap_ulong(unsigned long); unsigned short _byteswap_ushort(unsigned short); unsigned long long _byteswap_uint64(unsigned long long);
