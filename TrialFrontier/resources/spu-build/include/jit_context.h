#include "spu_context.h"
typedef void (*frontier_spu_fn)(spu_context*);
frontier_spu_fn* frontier_spu_tls_target(void);
uint32_t* frontier_spu_tls_history(void);
unsigned* frontier_spu_tls_history_count(void);
#define g_spu_trampoline_fn (*frontier_spu_tls_target())
#define g_spu_pch (frontier_spu_tls_history())
#define g_spu_pch_n (*frontier_spu_tls_history_count())
