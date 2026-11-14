#pragma once
#include <stddef.h>
#include <stdarg.h>
typedef struct { void *_Placeholder; } FILE;
FILE *__acrt_iob_func(unsigned);
#define stderr (__acrt_iob_func(2))
#define stdout (__acrt_iob_func(1))
int __stdio_common_vfprintf(unsigned long long, FILE*, const char*, void*, va_list);
static inline int fprintf(FILE *f,const char *fmt,...) { va_list a; va_start(a,fmt);int r=__stdio_common_vfprintf(0,f,fmt,0,a);va_end(a);return r; }
int fflush(FILE*);
