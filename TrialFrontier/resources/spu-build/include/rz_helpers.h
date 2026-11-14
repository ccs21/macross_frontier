/* Scoped SPU RZ arithmetic: caller sets MXCSR=0x7f80 and restores it.
 * Ordinary IEEE lanes use RZ SIMD; extended, denormal and boundary lanes
 * retain the exact SDK arithmetic. No fast-math is permitted. */
#pragma once
#include "spu_helpers.h"
#include <immintrin.h>
static inline int rz_plain(__m128i v) {
    __m128i abs=_mm_and_si128(v,_mm_set1_epi32(0x7fffffff));
    __m128i exp=_mm_and_si128(abs,_mm_set1_epi32(0x7f800000));
    __m128i normal=_mm_and_si128(_mm_cmpgt_epi32(exp,_mm_setzero_si128()),
                                _mm_cmpgt_epi32(_mm_set1_epi32(0x7f800000),exp));
    return _mm_movemask_epi8(_mm_or_si128(normal,_mm_cmpeq_epi32(abs,_mm_setzero_si128())))==65535;
}
static __attribute__((noinline)) u128 rz_exact(int op,u128 a,u128 b,u128 c) {
    switch(op) {
    case 0:return spu_fa(a,b); case 1:return spu_fm(a,b);
    case 2:return spu_fma(a,b,c); case 3:return spu_fms(a,b,c);
    case 4:return spu_fnms(a,b,c); default:return spu_fs(a,b);
    }
}
static inline u128 rz_candidate_scoped(int op,u128 a,u128 b,u128 c) {
    __m128i ai=_mm_loadu_si128((const __m128i*)&a),bi=_mm_loadu_si128((const __m128i*)&b);
    __m128i ci=_mm_loadu_si128((const __m128i*)&c);
    if(!rz_plain(ai)||!rz_plain(bi)||(op>=2&&op<=4&&!rz_plain(ci)))return rz_exact(op,a,b,c);
    __m128 x=_mm_castsi128_ps(ai),y=_mm_castsi128_ps(bi),z=_mm_castsi128_ps(ci),r;
    switch(op) {
    case 0:r=_mm_add_ps(x,y);break; case 1:r=_mm_mul_ps(x,y);break;
    case 2:r=_mm_fmadd_ps(x,y,z);break; case 3:r=_mm_fmsub_ps(x,y,z);break;
    case 4:r=_mm_fnmadd_ps(x,y,z);break; default:r=_mm_sub_ps(x,y);break;
    }
    __m128i bits=_mm_castps_si128(r),abs=_mm_and_si128(bits,_mm_set1_epi32(0x7fffffff));
    if(!rz_plain(bits)||_mm_movemask_epi8(_mm_or_si128(
         _mm_cmpeq_epi32(abs,_mm_set1_epi32(0x7f7fffff)),
         _mm_cmpeq_epi32(abs,_mm_set1_epi32(0x00800000)))))return rz_exact(op,a,b,c);
    u128 result;
    _mm_storeu_si128((__m128i*)&result,_mm_andnot_si128(_mm_cmpeq_epi32(abs,_mm_setzero_si128()),bits));
    return result;
}
