/* t3_token.c: one token of exact-16 (SmolLM2-135M) in the t3 machine, every step of it: the products, the
 * divisions and square roots, the roundings, clamps, comparisons and table reads. Arithmetic: add, subtract, shift,
 * bitwise logic and the sign test (the LOOK). No multiply or divide is written here; t3_nomul.py checks the object.
 *
 * Built two ways from this one file:
 *   host (T3_HOST): a shared library for exact_llm.py, LANES = 8, the weight products on threads, file reads by pread;
 *   freestanding (no T3_HOST): rv32i, LANES = 1, no libc, file reads by the caller's t3_io_read (main_rv32.c).
 * The model comes from one blob (exact_llm.py t3_blob): a directory of int64, then the tables, the norm weights,
 * the embedding (int32), the 16-bit weights, their row scales and their t3 streams.
 *
 * The machine's words, as t3.c (ADD i, SUB i, STEP, EMIT; op << 14 | i). Counters: t3k_cnt[site][class], one per
 * operation on data; loop control and address arithmetic are not counted. Classes:
 *   ADD     an add or subtract (a negation is 0 - x)        HORNER  the acc + acc of a Horner step
 *   SHIFT   a shift by a constant of the program            SHIFTV  a shift by an amount computed from the data
 *   LOGIC   and, or, xor                                    LOOK    a sign or zero test, or the read of one digit
 *   READ    a table entry read at an index computed from the data (exp, SiLU, cos, sin)
 */
#include <stdint.h>
#ifdef T3_HOST
#include <fcntl.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#endif

typedef int64_t i64;
typedef uint64_t u64;
typedef int32_t i32;
typedef uint32_t u32;
typedef int16_t i16;
typedef uint16_t u16;

#ifndef LANES
#define LANES 8
#endif
#define KEEP(v) __asm__ volatile("" : "+r"(v))

#define HID 576
#define NH 9
#define NKV 3
#define HD 64
#define FF 1536
#define NL 30
#define VOC 49152
#define VBLK 8192
#define NVB 6
#define NMAT 216                       /* 30 x 7 + 6 */
#define LIM 32767
#define EXPN 6144
#define SILUN 8192
#define DIRN 4096

enum { S_WEIGHT, S_PEEL, S_ATTN, S_MUL, S_DIV, S_SQRT, S_OTHER, S_CHECK, NSITE };
enum { C_ADD, C_HORNER, C_SHIFT, C_SHIFTV, C_LOGIC, C_LOOK, C_READ, C_SPARE, NCLS };   /* NCLS = 8 */
enum { K_RESID, K_ATTIN, K_Q, K_K, K_V, K_OIN, K_MLPIN, K_GATE, K_UP, K_DOWNIN, K_LOGIN };

u64 t3k_cnt[NSITE][NCLS];
u64 t3k_clamped, t3k_held, t3k_fail;
static int site;

#define CNT(c) (t3k_cnt[site][c] += 1)

/* ---- the operations, counted ---------------------------------------------------------------------------------- */
static inline i64 add(i64 a, i64 b) { CNT(C_ADD); return (i64)((u64)a + (u64)b); }
static inline i64 sub(i64 a, i64 b) { CNT(C_ADD); return (i64)((u64)a - (u64)b); }
static inline i64 shl(i64 a, int k) { CNT(C_SHIFT); return (i64)((u64)a << k); }
static inline i64 shr(i64 a, int k) { CNT(C_SHIFT); return a >> k; }
static inline i64 shlv(i64 a, i64 k) { CNT(C_SHIFTV); return (i64)((u64)a << k); }
static inline i64 shrv(i64 a, i64 k) { CNT(C_SHIFTV); return a >> k; }
static inline i64 and_(i64 a, i64 b) { CNT(C_LOGIC); return a & b; }
static inline int neg(i64 a) { CNT(C_LOOK); return a < 0; }             /* the LOOK */
static inline int iszero(i64 a) { CNT(C_LOOK); return a == 0; }
static inline i64 rd(const i64 *t, i64 i) { CNT(C_READ); return t[i]; }
static inline int lt(i64 a, i64 b) { return neg(sub(a, b)); }           /* a < b */
static inline i64 absv(i64 a) { return neg(a) ? sub(0, a) : a; }
static inline i64 maxv(i64 a, i64 b) { return lt(a, b) ? b : a; }
static inline i64 minv(i64 a, i64 b) { return lt(b, a) ? b : a; }
/* round(v 2^-k), halves up, k a constant of the program (k >= 1) */
static inline i64 rshift_round(i64 v, int k) { return shr(add(v, (i64)1 << (k - 1)), k); }
/* round(v 2^-k), halves up, k from the data (k >= 0): (v + ((1 << k) >> 1)) >> k, as shift_round in exact_llm.py */
static inline i64 shift_round(i64 v, i64 k) { return shrv(add(v, shr(shlv(1, k), 1)), k); }
/* the same with k a constant of the program read from a table (the row scales g) */
static inline i64 shift_round_g(i64 v, i64 g) {
    CNT(C_SHIFT);
    return add(v, (i64)(((u64)1 << g) >> 1)) >> g;
}

static __attribute__((unused)) void zero_bytes(void *p, u64 n) {
    unsigned char *c = (unsigned char *)p;
    while (n) {
        *c++ = 0;
        n -= 1;
    }
}

/* a * b for addresses only (not a model operation, not counted): shift and add over the bits of b */
static u64 addr_mul(u64 a, u64 b) {
    u64 r = 0;
    while (b) {
        if (b & 1u)
            r += a;
        a += a;
        b >>= 1;
        KEEP(r);                                 /* else the compiler sees the multiply and emits one */
        KEEP(a);
    }
    return r;
}

/* ---- signed digits and the element-wise product ----------------------------------------------------------------- */
/* digits of v (|v| < 2^62): plus and minus masks, v = plus - minus. Counted: the sign look, the negation, 1 shift,
 * 1 add, 3 logic. */
static inline void recode(i64 v, u64 *pl, u64 *mi) {
    int ng = neg(v);
    u64 m = (u64)(ng ? sub(0, v) : v);
    u64 h = (u64)shr((i64)m, 1);
    u64 s = (u64)add((i64)m, (i64)h);
    u64 c = h ^ s;
    u64 p = s & c, q = h & c;
    CNT(C_LOGIC);
    CNT(C_LOGIC);
    CNT(C_LOGIC);
    *pl = ng ? q : p;
    *mi = ng ? p : q;
}

/* a * b, |b| < 2^K: b's digits read from position K down (one LOOK per position), Horner on a. Mod 2^64. */
static i64 mul_sd(i64 a, i64 b, int K) {
    u64 pl, mi;
    recode(b, &pl, &mi);
    i64 acc = 0;
    u64 bit = (u64)1 << K;
    while (bit) {
        acc = (i64)((u64)acc + (u64)acc);
        CNT(C_HORNER);
        CNT(C_LOOK);
        if (pl & bit)
            acc = add(acc, a);
        else if (mi & bit)
            acc = sub(acc, a);
        bit >>= 1;
    }
    return acc;
}

/* ---- division and square root: digit recurrences of subtract, double and the sign test ------------------------ */
/* floor(num / den), den > 0, |num| < 2^62: as fdiv in exact_llm.py (NumPy's //), with its bracket checked:
 * the remainder r of |num| satisfies 0 <= r < den. Restoring division on the magnitude: den doubled until the next
 * double passes |num| (one LOOK each), then per quotient digit: q = q + q, t = r - d, LOOK t, keep t and q + 1 if
 * t >= 0, d halved. A negative num: q = -q, minus 1 more if r != 0 (a zero LOOK). */
static i64 fdiv(i64 num, i64 den) {
    int sv = site;
    site = S_DIV;
    int ng = neg(num);
    i64 n = ng ? sub(0, num) : num;
    i64 d = den, k = 0;
    for (;;) {
        i64 d2 = add(d, d);
        if (neg(sub(n, d2)))
            break;
        d = d2;
        k += 1;
    }
    i64 q = 0, r = n;
    for (;;) {
        q = add(q, q);
        i64 t = sub(r, d);
        if (!neg(t)) {
            r = t;
            q = add(q, 1);
        }
        if (k == 0)
            break;
        k -= 1;
        d = shr(d, 1);
    }
    if (ng) {
        q = sub(0, q);
        if (!iszero(r))
            q = sub(q, 1);
    }
    site = S_CHECK;
    if (!neg(sub(r, den)))
        t3k_fail += 1;
    site = sv;
    return q;
}

/* floor(sqrt(n)), 0 <= n < 2^62, as isqrt in exact_llm.py, bracket s^2 <= n < (s + 1)^2 checked as the remainder
 * n - s^2 <= 2 s. Digit by digit: the highest power of 4 at or below n (one LOOK per step down), then per digit
 * t = res + bit, LOOK (r - t): keep r - t and res / 2 + bit, else res / 2; bit / 4. */
static i64 isqrt(i64 n) {
    int sv = site;
    site = S_SQRT;
    i64 bit = (i64)1 << 62;
    while (bit != 0 && neg(sub(n, bit)))
        bit = shr(bit, 2);
    i64 res = 0, r = n;
    while (bit != 0) {
        i64 d = sub(r, add(res, bit));
        if (!neg(d)) {
            r = d;
            res = add(shr(res, 1), bit);
        } else {
            res = shr(res, 1);
        }
        bit = shr(bit, 2);
    }
    site = S_CHECK;
    if (neg(sub(add(res, res), r)))
        t3k_fail += 1;
    site = sv;
    return res;
}

/* ---- the stream machine -------------------------------------------------------------------------------------- */
/* rows [r0, r1) of a stream; xrow[i] the inputs of input i (lanes contiguous); yrow[r] the outputs of row r. Lanes run
 * LANES at a time over nlanes (inputs readable up to the next multiple of LANES); the counters count real lanes. */
static void run_rows(const u16 *stream, const i64 *rowoff, i64 r0, i64 r1, i64 rstep, const i32 *const *xrow,
                     i64 nlanes, i64 *const *yrow, u64 *adds, u64 *horner) {
    u64 a = 0, h = 0;
    for (i64 r = r0; r < r1; r += rstep) {
        const u16 *start = stream + rowoff[r];
        i64 *y = yrow[r];
        i64 left = nlanes;
        for (i64 c = 0; c < nlanes; c += LANES) {
            u64 nl = left < LANES ? (u64)left : (u64)LANES;
            left -= LANES;
            const u16 *p = start;
#if LANES == 8
            /* 8 lanes as vector types: two registers of s, four of acc (t3.c's form) */
            typedef u32 v8 __attribute__((vector_size(32)));
            typedef u64 v8l __attribute__((vector_size(64)));
            typedef i32 v8s __attribute__((vector_size(32)));
            typedef i64 v8ls __attribute__((vector_size(64)));
            v8 s = {0, 0, 0, 0, 0, 0, 0, 0};
            v8l acc = {0, 0, 0, 0, 0, 0, 0, 0};
            for (;;) {
                u32 w = *p++;
                u32 op = w >> 14;
                if (op == 0u) {
                    v8 xv;
                    __builtin_memcpy(&xv, xrow[w & 0x3FFFu] + c, sizeof xv);
                    s += xv;
                    a += nl;
                } else if (op == 1u) {
                    v8 xv;
                    __builtin_memcpy(&xv, xrow[w & 0x3FFFu] + c, sizeof xv);
                    s -= xv;
                    a += nl;
                } else {
                    acc = acc + acc;
                    acc = acc + (v8l)__builtin_convertvector((v8s)s, v8ls);
                    s = (v8){0, 0, 0, 0, 0, 0, 0, 0};
                    h += nl;
                    h += nl;
                    if (op == 3u)
                        break;
                }
            }
            u64 out[8];
            __builtin_memcpy(out, &acc, sizeof acc);
#else
            u32 s[LANES];
            u64 out[LANES];
            for (int j = 0; j < LANES; j++) {
                s[j] = 0;
                out[j] = 0;
            }
            for (;;) {
                u32 w = *p++;
                u32 op = w >> 14;
                if (op == 0u) {
                    const i32 *xr = xrow[w & 0x3FFFu] + c;
                    for (int j = 0; j < LANES; j++)
                        s[j] += (u32)xr[j];
                    a += nl;
                } else if (op == 1u) {
                    const i32 *xr = xrow[w & 0x3FFFu] + c;
                    for (int j = 0; j < LANES; j++)
                        s[j] -= (u32)xr[j];
                    a += nl;
                } else {
                    for (int j = 0; j < LANES; j++) {
                        out[j] = out[j] + out[j];
                        out[j] = out[j] + (u64)(i64)(i32)s[j];
                        s[j] = 0;
                    }
                    h += nl;
                    h += nl;
                    if (op == 3u)
                        break;
                }
            }
#endif
            for (int j = 0; j < LANES && j < (int)(nlanes - c); j++)
                y[c + j] = (i64)out[j];
        }
    }
    *adds += a;
    *horner += h;
}

#ifdef T3_HOST
typedef struct {
    const u16 *stream;
    const i64 *rowoff;
    i64 r0, r1, rstep, nlanes;
    const i32 *const *xrow;
    i64 *const *yrow;
    u64 adds, horner;
    i64 pad[6];                                         /* 128 bytes: an index is a shift */
} job_t;

static void *job_run(void *arg) {
    job_t *j = (job_t *)arg;
    run_rows(j->stream, j->rowoff, j->r0, j->r1, j->rstep, j->xrow, j->nlanes, j->yrow, &j->adds, &j->horner);
    return 0;
}
static i64 nthreads = 1;
#endif

/* y = the stream's rows on the inputs, rows 0..M-1; counted at the current site */
static void run_stream(const u16 *stream, const i64 *rowoff, i64 M, const i32 *const *xrow, i64 nlanes,
                       i64 *const *yrow) {
    u64 a = 0, h = 0;
#ifdef T3_HOST
    if (nthreads > 1 && M >= 64) {
        job_t jobs[64];
        pthread_t th[64];
        char started[64];
        i64 nt = nthreads > 64 ? 64 : nthreads;
        for (i64 t = 0; t < nt; t++) {                  /* rows interleaved: thread t takes t, t + nt, ... */
            job_t *j = &jobs[t];
            j->stream = stream;
            j->rowoff = rowoff;
            j->r0 = t;
            j->r1 = M;
            j->rstep = nt;
            j->nlanes = nlanes;
            j->xrow = xrow;
            j->yrow = yrow;
            j->adds = 0;
            j->horner = 0;
            started[t] = pthread_create(&th[t], 0, job_run, j) == 0;
            if (!started[t])
                job_run(j);                             /* a thread that could not start: its rows run here */
        }
        for (i64 t = 0; t < nt; t++) {
            if (started[t])
                pthread_join(th[t], 0);
            a += jobs[t].adds;
            h += jobs[t].horner;
        }
    } else
#endif
        run_rows(stream, rowoff, 0, M, 1, xrow, nlanes, yrow, &a, &h);
    t3k_cnt[site][C_ADD] += a;
    t3k_cnt[site][C_HORNER] += h;
}

/* one output row from n values at run time (|v| <= 2^15 - 1): recode each (counted), then per position k = 15..0 one
 * digit read (LOOK) per value; words ADD i, then SUB i, then STEP (EMIT at k = 0). Returns the word count. */
static i64 compile_row(const i64 *v, i64 n, u16 *out, u16 *subs, u16 *pm, u16 *mm) {
    for (i64 i = 0; i < n; i++) {
        u64 p, q;
        recode(v[i], &p, &q);
        pm[i] = (u16)p;
        mm[i] = (u16)q;
    }
    u16 *o = out;
    u32 bit = 1u << 15;
    while (bit) {
        u16 *sb = subs;
        for (i64 i = 0; i < n; i++) {
            CNT(C_LOOK);
            if (pm[i] & bit)
                *o++ = (u16)i;
            else if (mm[i] & bit)
                *sb++ = (u16)((1u << 14) | (u32)i);
        }
        for (u16 *t = subs; t < sb; t++)
            *o++ = *t;
        bit >>= 1;
        *o++ = (u16)((bit ? 2u : 3u) << 14);
    }
    return o - out;
}

/* ---- the model ------------------------------------------------------------------------------------------------ */
typedef struct {                       /* 16 x 8 bytes */
    i64 n_in, M, off_words, nwords, off_rowoff, off_w16, ld, c0, off_g, clampsite;
    const i64 *rowoff, *g;
    i64 spare[4];
} mat_t;

extern int t3_io_read(u64 off, void *dst, u64 n);          /* the blob, from byte off */

static i64 dirv[DIRN];
static mat_t mats[NMAT];
static i64 clampv[11], epsv[17], normK, normbits;
static i64 *Et, *St, *Cos, *Sin, *Norm;                    /* Norm: 61 x 576, n1[0..29], n2[0..29], final */
static u16 *sbuf;                                          /* the stream of the product being run */
static i16 *wrow;                                          /* peel weight rows: 2 x 8,192 */
static const i32 *xrowt[16384];
static i64 *yrowt[16384];
static i64 nslots, mp;                                     /* slots (sequences), positions per slot (padded) */
static i32 *kc, *vh, *vl;                                  /* [slot][layer][kv][64][mp], [slot][layer][kv][mp][64] */
static i64 *shk;                                           /* [slot][layer][kv][mp] */
/* per-lane activations and scratch, for up to NLANE lanes */
static i64 nlane_max;
static i64 *X, *H, *Q, *Kx, *Vx, *CTX, *G, *U, *Y;         /* [lane][dim] */
static i32 *X16;                                           /* [dim][lanes padded] */
static i64 *T;                                             /* [M][lanes padded] */
static i64 *sh_l, *xp_l, *ip_l;                            /* per lane: shift; 2 peeled values; 2 indices */
static u16 *qs, *qsub, *qpm, *qmm;                         /* run-time streams (q, p) */
static i64 *att_s, *att_e, *att_p, *ch, *cl, *q16, *vtmp, *vtmp2;

static int rd_i64(u64 off, i64 *dst, u64 n) { return t3_io_read(off, dst, n << 3); }

#ifdef T3_HOST
static int fd = -1;
int t3_io_read(u64 off, void *dst, u64 n) {
    unsigned char *d = (unsigned char *)dst;
    while (n) {
        ssize_t r = pread(fd, d, n, (off_t)off);
        if (r <= 0)
            return -1;
        d += r;
        off += (u64)r;
        n -= (u64)r;
    }
    return 0;
}
static void *alloc(u64 n) { return calloc(1, n ? n : 1); }
#else
/* freestanding: one arena, given by main */
static unsigned char *arena;
static u64 arena_left;
static void *alloc(u64 n) {
    n = (n + 15u) & ~(u64)15u;
    if (n > arena_left)
        return 0;
    void *p = arena;
    arena += n;
    arena_left -= n;
    zero_bytes(p, n);
    return p;
}
void t3k_arena(void *base, u64 size) {
    arena = (unsigned char *)base;
    arena_left = size;
}
#endif

/* open the model: lanes (sequences at once), positions per sequence. Returns 0, or a negative step that failed. */
int t3k_open_model(i64 slots, i64 positions, i64 threads) {
#ifdef T3_HOST
    nthreads = threads;
#else
    (void)threads;
#endif
    if (rd_i64(0, dirv, DIRN))
        return -1;
    if (dirv[0] != 0x5433424C4F423031LL || dirv[2] != HID || dirv[7] != NL || dirv[8] != VOC)
        return -2;
    normbits = dirv[9];
    normK = dirv[10];
    for (int i = 0; i < 11; i++)
        clampv[i] = dirv[16 + i];
    for (int i = 0; i < 17; i++)
        epsv[i] = dirv[32 + i];
    Et = (i64 *)alloc((u64)(EXPN + 1) << 3);
    St = (i64 *)alloc((u64)(SILUN + 1) << 3);
    Cos = (i64 *)alloc((u64)16384 << 3);
    Sin = (i64 *)alloc((u64)16384 << 3);
    Norm = (i64 *)alloc(addr_mul(61, HID) << 3);
    if (!Et || !St || !Cos || !Sin || !Norm)
        return -3;
    if (rd_i64((u64)dirv[64], Et, EXPN + 1) || rd_i64((u64)dirv[66], St, SILUN + 1) ||
        rd_i64((u64)dirv[68], Cos, 16384) || rd_i64((u64)dirv[69], Sin, 16384) ||
        rd_i64((u64)dirv[71], Norm, addr_mul(61, HID)))
        return -4;
    u64 maxwords = 0;
    const i64 *de = dirv + 128;
    for (int m = 0; m < NMAT; m++) {
        mat_t *t = &mats[m];
        t->n_in = de[0];
        t->M = de[1];
        t->off_words = de[2];
        t->nwords = de[3];
        t->off_rowoff = de[4];
        t->off_w16 = de[5];
        t->ld = de[6];
        t->c0 = de[7];
        t->off_g = de[8];
        t->clampsite = de[9];
        de += 16;
        i64 *ro = (i64 *)alloc((u64)(t->M + 1) << 3);
        i64 *g = (i64 *)alloc((u64)t->M << 3);
        if (!ro || !g || rd_i64((u64)t->off_rowoff, ro, (u64)t->M + 1) || rd_i64((u64)t->off_g, g, (u64)t->M))
            return -5;
        t->rowoff = ro;
        t->g = g;
        if ((u64)t->nwords > maxwords)
            maxwords = (u64)t->nwords;
    }
    sbuf = (u16 *)alloc(maxwords << 1);
    wrow = (i16 *)alloc((u64)VBLK << 2);
    nslots = slots;
    mp = (positions + 63) & ~(i64)63;
    u64 kvn = addr_mul(addr_mul((u64)slots, NL), NKV);              /* slot x layer x kv */
    kc = (i32 *)alloc(addr_mul(kvn, (u64)mp) << 8);                  /* x 64 x 4 bytes */
    vh = (i32 *)alloc(addr_mul(kvn, (u64)mp) << 8);
    vl = (i32 *)alloc(addr_mul(kvn, (u64)mp) << 8);
    shk = (i64 *)alloc(addr_mul(kvn, (u64)mp) << 3);
    nlane_max = slots;
    u64 L = (u64)slots, LP = (u64)((slots + LANES - 1) & ~(i64)(LANES - 1));
    X = (i64 *)alloc(addr_mul(L, HID) << 3);
    H = (i64 *)alloc(addr_mul(L, HID) << 3);
    Q = (i64 *)alloc(addr_mul(L, HID) << 3);
    Kx = (i64 *)alloc(addr_mul(L, 192) << 3);
    Vx = (i64 *)alloc(addr_mul(L, 192) << 3);
    CTX = (i64 *)alloc(addr_mul(L, HID) << 3);
    G = (i64 *)alloc(addr_mul(L, FF) << 3);
    U = (i64 *)alloc(addr_mul(L, FF) << 3);
    Y = (i64 *)alloc(addr_mul(L, VBLK) << 3);
    X16 = (i32 *)alloc(addr_mul(LP, FF) << 2);
    T = (i64 *)alloc(addr_mul(LP, VBLK) << 3);
    sh_l = (i64 *)alloc(L << 3);
    xp_l = (i64 *)alloc(L << 4);
    ip_l = (i64 *)alloc(L << 4);
    u64 qn = (u64)mp + 64;
    qs = (u16 *)alloc((qn << 5) + 64);
    qsub = (u16 *)alloc((qn << 1) + 16);
    qpm = (u16 *)alloc(qn << 1);
    qmm = (u16 *)alloc(qn << 1);
    att_s = (i64 *)alloc((u64)mp << 3);
    att_e = (i64 *)alloc((u64)mp << 3);
    att_p = (i64 *)alloc((u64)mp << 3);
    ch = (i64 *)alloc(64 << 3);
    cl = (i64 *)alloc(64 << 3);
    q16 = (i64 *)alloc(64 << 3);
    vtmp = (i64 *)alloc((u64)FF << 3);
    vtmp2 = (i64 *)alloc((u64)FF << 3);
    if (!sbuf || !wrow || !kc || !vh || !vl || !shk || !X || !T || !qs || !vtmp || !vtmp2)
        return -6;
    return 0;
}

static void clampvec(i64 *x, i64 n, int k) {
    i64 c = clampv[k];
    site = S_OTHER;
    for (i64 i = 0; i < n; i++) {
        if (neg(sub(c, x[i]))) {
            x[i] = c;
            t3k_clamped += 1;
        } else if (neg(add(x[i], c))) {
            x[i] = sub(0, c);
            t3k_clamped += 1;
        }
    }
}

static i64 bitlen(i64 t) {                     /* t >= 0: shift right until zero, one LOOK per step */
    i64 b = 0;
    while (!iszero(t)) {
        t = shr(t, 1);
        b = add(b, 1);
    }
    return b;
}

/* block16: out = round(x 2^-sh), the least sh >= 0 with every |out| <= 2^15 - 1 (one more if the rounding needs it) */
static i64 block16(const i64 *x, i64 n, i64 *out) {
    site = S_OTHER;
    i64 top = 0;
    for (i64 i = 0; i < n; i++)
        top = maxv(top, absv(x[i]));
    i64 sh = sub(bitlen(top), 15);
    if (neg(sh))
        sh = 0;
    int over = 0;
    for (i64 i = 0; i < n; i++) {
        out[i] = shift_round(x[i], sh);
        if (lt(LIM, absv(out[i])))
            over = 1;
    }
    if (over) {
        sh = add(sh, 1);
        for (i64 i = 0; i < n; i++)
            out[i] = shift_round(x[i], sh);
    }
    return sh;
}


/* A product input as every product that reads it needs it, made once (exact_llm.py prepare, looks once): its 2
 * largest |x| taken out whole, the rest block-shifted to 16 bits per lane. x [lane][n] (clamped by the caller);
 * fills X16 [n][lanes padded], sh_l, xp_l, ip_l. */
static i64 prep_n;
static void prepare(i64 N, const i64 *x, i64 n) {
    i64 LP = (N + LANES - 1) & ~(i64)(LANES - 1);
    const i64 *xl = x;
    prep_n = n;
    for (i64 l = 0; l < N; l++) {
        site = S_OTHER;
        /* the 2 largest |x|, ties to the lower index: keys |x| 2^11 + (2^11 - 1 - i) */
        i64 k1 = -1, k2 = -1, i1 = 0, i2 = 0;
        for (i64 i = 0; i < n; i++) {
            i64 key = add(shl(absv(xl[i]), 11), 2047 - i);
            if (lt(k1, key)) {
                k2 = k1;
                i2 = i1;
                k1 = key;
                i1 = i;
            } else if (lt(k2, key)) {
                k2 = key;
                i2 = i;
            }
        }
        for (i64 i = 0; i < n; i++)
            vtmp[i] = xl[i];
        xp_l[l + l] = vtmp[i1];
        xp_l[l + l + 1] = vtmp[i2];
        ip_l[l + l] = i1;
        ip_l[l + l + 1] = i2;
        vtmp[i1] = 0;
        vtmp[i2] = 0;
        sh_l[l] = block16(vtmp, n, vtmp2);
        i32 *col = X16 + l;
        for (i64 i = 0; i < n; i++) {               /* X16 [i][lane] */
            *col = (i32)vtmp2[i];
            col += LP;
        }
        xl += n;
        KEEP(xl);
    }
    for (i64 l = N; l < LP; l++) {                  /* padded lanes: zero inputs */
        i32 *col = X16 + l;
        for (i64 i = 0; i < n; i++) {
            *col = 0;
            col += LP;
        }
    }
}

/* y [lane][M] = round(2^-g (2^sh x16 . w16 + peeled x w16)) for the matrix m on the input prepare() made last;
 * int32 output if y32 (lane stride ldy32) */
static void product(i64 N, const mat_t *m, i64 *y, i32 *y32, i64 ldy32) {
    i64 n = m->n_in, M = m->M;
    i64 LP = (N + LANES - 1) & ~(i64)(LANES - 1);
    if (n != prep_n)
        t3k_fail += 1;
    const i32 *xr = X16;
    for (i64 i = 0; i < n; i++) {
        xrowt[i] = xr;
        xr += LP;
        KEEP(xr);
    }
    i64 *yr = T;
    for (i64 r = 0; r < M; r++) {
        yrowt[r] = yr;
        yr += LP;
        KEEP(yr);
    }
    t3_io_read((u64)m->off_words, sbuf, (u64)m->nwords << 1);
    site = S_WEIGHT;
    run_stream(sbuf, m->rowoff, M, xrowt, N, yrowt);
    i64 *yl = y;
    i32 *y32l = y32;
    for (i64 l = 0; l < N; l++) {
        for (int j = 0; j < 2; j++) {                 /* the two weight rows of the peeled inputs */
            u64 off = (u64)m->off_w16 + (addr_mul((u64)ip_l[l + l + j], (u64)m->ld) << 1) + ((u64)m->c0 << 1);
            t3_io_read(off, wrow + (j ? VBLK : 0), (u64)M << 1);
        }
        i64 sh = sh_l[l], xp1 = xp_l[l + l], xp2 = xp_l[l + l + 1];
        const i64 *tr = T + l;
        for (i64 r = 0; r < M; r++) {
            site = S_OTHER;
            i64 t = shlv(*tr, sh);
            site = S_PEEL;
            t = add(t, mul_sd(xp1, wrow[r], 15));
            t = add(t, mul_sd(xp2, wrow[VBLK + r], 15));
            site = S_OTHER;
            i64 v = shift_round_g(t, m->g[r]);
            if (y32)
                y32l[r] = (i32)v;
            else
                yl[r] = v;
            tr += LP;
        }
        yl += M;
        KEEP(yl);
        if (y32) {
            y32l += ldy32;
            KEEP(y32l);
        }
    }
}

/* RMS norm of one vector x [576] at 2^-16 with weight w; as Exact.rms */
static void rms(const i64 *x, const i64 *w, i64 *y) {
    site = S_OTHER;
    i64 top = 0;
    for (int i = 0; i < HID; i++)
        top = maxv(top, absv(x[i]));
    i64 sh = sub(bitlen(top), normbits);
    if (neg(sh))
        sh = 0;
    i64 ss = 0;
    for (int i = 0; i < HID; i++) {
        site = S_OTHER;
        i64 xs = shrv(x[i], sh);
        site = S_MUL;
        ss = add(ss, mul_sd(xs, xs, (int)normbits));
    }
    i64 ms = fdiv(ss, HID);
    site = S_OTHER;
    i64 r = isqrt(add(ms, epsv[sh]));
    i64 up = sub(16, sh);
    for (int i = 0; i < HID; i++) {
        site = S_OTHER;
        i64 v = fdiv(shlv(x[i], up), r);
        site = S_MUL;
        v = mul_sd(v, w[i], (int)normK);
        site = S_OTHER;
        y[i] = rshift_round(v, 16);
    }
}

static void rope(i64 *x, i64 pos) {             /* one head vector of 64, cos and sin of the position at 2^-20 */
    const i64 *c = Cos, *s = Sin;
    for (i64 p = 0; p < pos; p++) {             /* row pos of the [512][32] tables (address only) */
        c += 32;
        s += 32;
    }
    for (int i = 0; i < 32; i++) {
        site = S_OTHER;
        i64 ci = rd(c, i), si = rd(s, i);
        i64 x1 = x[i], x2 = x[i + 32];
        site = S_MUL;
        i64 a = sub(mul_sd(x1, ci, 21), mul_sd(x2, si, 21));
        i64 b = add(mul_sd(x2, ci, 21), mul_sd(x1, si, 21));
        site = S_OTHER;
        x[i] = rshift_round(a, 20);
        x[i + 32] = rshift_round(b, 20);
    }
}

static i64 expt(i64 t) {                        /* t >= 0 */
    site = S_OTHER;
    i64 k = minv(shr(t, 8), EXPN);
    i64 r = and_(t, 255);
    i64 e0 = rd(Et, k), e1 = rd(Et, minv(add(k, 1), EXPN));
    site = S_MUL;
    i64 v = add(mul_sd(e0, sub(256, r), 9), mul_sd(e1, r, 9));
    site = S_OTHER;
    return shr(v, 8);
}

static i64 silu(i64 x) {
    site = S_OTHER;
    i64 top = (i64)SILUN << 8;
    i64 u = add(x, (i64)16 << 16);
    i64 uc = u;
    if (neg(uc))
        uc = 0;
    else if (!lt(uc, top))
        uc = top - 1;
    i64 k = shr(uc, 8), r = and_(uc, 255);
    i64 s0 = rd(St, k), s1 = rd(St, add(k, 1));
    site = S_MUL;
    i64 g = add(mul_sd(s0, sub(256, r), 9), mul_sd(s1, r, 9));
    site = S_OTHER;
    g = shr(g, 8);
    if (neg(u))
        return 0;
    if (lt(u, top))
        return g;
    return x;
}

/* the cache arrays of one slot and layer (addresses only) */
static void cache_at(i64 slot, i64 layer, i32 **k, i32 **vhp, i32 **vlp, i64 **shp) {
    u64 blk = addr_mul(addr_mul((u64)slot, NL) + (u64)layer, NKV);
    *k = kc + (addr_mul(blk, (u64)mp) << 6);
    *vhp = vh + (addr_mul(blk, (u64)mp) << 6);
    *vlp = vl + (addr_mul(blk, (u64)mp) << 6);
    *shp = shk + addr_mul(blk, (u64)mp);
}

/* attention of one lane at position pos (keys 0..pos, its own cache): q [576] after rope, ctx [576] out */
static void attention(i64 slot, i64 layer, i64 pos, i64 *q, i64 *ctx) {
    i32 *kb, *vhb, *vlb;
    i64 *shb;
    cache_at(slot, layer, &kb, &vhb, &vlb, &shb);
    i64 nk = pos + 1;
    i64 *qh = q, *ch_out = ctx;
    for (int kv = 0; kv < NKV; kv++) {
        const i32 *xr = kb;                                  /* scores: inputs are the 64 dims, lanes the keys */
        for (int i = 0; i < 64; i++) {
            xrowt[i] = xr;
            xr += mp;
            KEEP(xr);
        }
        for (int g = 0; g < 3; g++) {
            clampvec(qh, 64, K_Q);
            i64 shq = block16(qh, 64, q16);
            site = S_ATTN;
            i64 nw = compile_row(q16, 64, qs, qsub, qpm, qmm);
            (void)nw;
            yrowt[0] = att_s;
            i64 nr = 0;
            run_stream(qs, &nr, 1, xrowt, nk, yrowt);
            site = S_OTHER;
            i64 mx = 0;
            for (i64 t = 0; t < nk; t++) {
                att_s[t] = shlv(att_s[t], add(shq, shb[t]));
                mx = t ? maxv(mx, att_s[t]) : att_s[t];
            }
            i64 se = 0;
            for (i64 t = 0; t < nk; t++) {
                i64 d = sub(mx, att_s[t]);
                if (neg(d))
                    d = 0;
                att_e[t] = expt(shr(d, 19));
                site = S_OTHER;
                se = add(se, att_e[t]);
            }
            for (i64 t = 0; t < nk; t++) {
                i64 p = fdiv(shl(att_e[t], 16), se);
                site = S_OTHER;
                p = rshift_round(p, 1);
                if (lt(LIM, p)) {
                    p = LIM;
                    t3k_held += 1;
                }
                att_p[t] = p;
            }
            site = S_ATTN;
            compile_row(att_p, nk, qs, qsub, qpm, qmm);      /* context: inputs are the keys, lanes the 64 dims */
            const i32 *vr = vhb;
            for (i64 t = 0; t < nk; t++) {
                xrowt[t] = vr;
                vr += 64;
                KEEP(vr);
            }
            yrowt[0] = ch;
            run_stream(qs, &nr, 1, xrowt, 64, yrowt);
            vr = vlb;
            for (i64 t = 0; t < nk; t++) {
                xrowt[t] = vr;
                vr += 64;
                KEEP(vr);
            }
            yrowt[0] = cl;
            run_stream(qs, &nr, 1, xrowt, 64, yrowt);
            site = S_OTHER;
            for (int d = 0; d < 64; d++)
                ch_out[d] = rshift_round(add(shl(ch[d], 15), cl[d]), 15);
            xr = kb;                                          /* the score rows again for the next head */
            for (int i = 0; i < 64; i++) {
                xrowt[i] = xr;
                xr += mp;
                KEEP(xr);
            }
            qh += 64;
            ch_out += 64;
        }
        kb += mp << 6;
        vhb += mp << 6;
        vlb += mp << 6;
        shb += mp;
    }
}

/* the new position's k and v into the cache: k clamped and block-shifted per head, v clamped and split */
static void cache_entry(i64 slot, i64 layer, i64 pos, i64 *k, i64 *v) {
    i32 *kb, *vhb, *vlb;
    i64 *shb;
    cache_at(slot, layer, &kb, &vhb, &vlb, &shb);
    clampvec(k, 192, K_K);
    clampvec(v, 192, K_V);
    for (int kv = 0; kv < NKV; kv++) {
        shb[pos] = block16(k, 64, q16);
        i32 *col = kb + pos;
        for (int d = 0; d < 64; d++) {
            *col = (i32)q16[d];
            col += mp;
        }
        i32 *hr = vhb + (pos << 6), *lr = vlb + (pos << 6);
        site = S_OTHER;
        for (int d = 0; d < 64; d++) {
            hr[d] = (i32)shr(v[d], 15);
            lr[d] = (i32)and_(v[d], LIM);
        }
        k += 64;
        v += 64;
        kb += mp << 6;
        vhb += mp << 6;
        vlb += mp << 6;
        shb += mp;
    }
}

/* one step for n lanes: lane l is slot slots[l] at position pos[l] with input token tok[l]; logits [n][49152]
 * int32 and the greedy next token. Returns 0. */
int t3k_step(i64 n, const i64 *slots, const i64 *tok, const i64 *pos, i32 *logits, i64 *next) {
    i64 *xl = X;
    for (i64 l = 0; l < n; l++) {                              /* the embedding row (data movement) */
        i32 row[HID];
        t3_io_read((u64)dirv[70] + (addr_mul((u64)tok[l], HID) << 2), row, HID << 2);
        for (int i = 0; i < HID; i++)
            xl[i] = row[i];
        xl += HID;
        KEEP(xl);
    }
    const mat_t *mm = mats;
    const i64 *n1 = Norm, *n2 = Norm + addr_mul(NL, HID);
    for (i64 layer = 0; layer < NL; layer++) {
        xl = X;
        i64 *hl = H;
        for (i64 l = 0; l < n; l++) {
            clampvec(xl, HID, K_RESID);
            rms(xl, n1, hl);
            clampvec(hl, HID, K_ATTIN);
            xl += HID;
            KEEP(xl);
            hl += HID;
            KEEP(hl);
        }
        prepare(n, H, HID);                                     /* one input, three products */
        product(n, mm + 0, Q, 0, 0);
        product(n, mm + 1, Kx, 0, 0);
        product(n, mm + 2, Vx, 0, 0);
        i64 *ql = Q, *kl = Kx, *vl_ = Vx, *cl_ = CTX;
        for (i64 l = 0; l < n; l++) {
            i64 *qh = ql;
            for (int h = 0; h < NH; h++) {
                rope(qh, pos[l]);
                qh += 64;
            }
            i64 *kh = kl;
            for (int h = 0; h < NKV; h++) {
                rope(kh, pos[l]);
                kh += 64;
            }
            cache_entry(slots[l], layer, pos[l], kl, vl_);
            attention(slots[l], layer, pos[l], ql, cl_);
            clampvec(cl_, HID, K_OIN);
            ql += HID;
            KEEP(ql);
            kl += 192;
            KEEP(kl);
            vl_ += 192;
            KEEP(vl_);
            cl_ += HID;
            KEEP(cl_);
        }
        prepare(n, CTX, HID);
        product(n, mm + 3, Y, 0, 0);
        xl = X;
        hl = H;
        i64 *yl = Y;
        for (i64 l = 0; l < n; l++) {
            site = S_OTHER;
            for (int i = 0; i < HID; i++)
                xl[i] = add(xl[i], yl[i]);
            clampvec(xl, HID, K_RESID);
            rms(xl, n2, hl);
            clampvec(hl, HID, K_MLPIN);
            xl += HID;
            KEEP(xl);
            hl += HID;
            KEEP(hl);
            yl += HID;
            KEEP(yl);
        }
        prepare(n, H, HID);
        product(n, mm + 4, G, 0, 0);
        product(n, mm + 5, U, 0, 0);
        i64 *gl = G, *ul = U;
        for (i64 l = 0; l < n; l++) {
            clampvec(gl, FF, K_GATE);
            clampvec(ul, FF, K_UP);
            for (int i = 0; i < FF; i++) {
                i64 sg = silu(gl[i]);
                site = S_MUL;
                i64 a = mul_sd(sg, ul[i], 32);
                site = S_OTHER;
                gl[i] = rshift_round(a, 16);
            }
            clampvec(gl, FF, K_DOWNIN);
            gl += FF;
            KEEP(gl);
            ul += FF;
            KEEP(ul);
        }
        prepare(n, G, FF);
        product(n, mm + 6, Y, 0, 0);
        xl = X;
        yl = Y;
        for (i64 l = 0; l < n; l++) {
            site = S_OTHER;
            for (int i = 0; i < HID; i++)
                xl[i] = add(xl[i], yl[i]);
            xl += HID;
            KEEP(xl);
            yl += HID;
            KEEP(yl);
        }
        mm += 7;
        n1 += HID;
        KEEP(n1);
        n2 += HID;
        KEEP(n2);
    }
    const i64 *nf = Norm + addr_mul(NL + NL, HID);
    xl = X;
    i64 *hl = H;
    for (i64 l = 0; l < n; l++) {
        clampvec(xl, HID, K_RESID);
        rms(xl, nf, hl);
        clampvec(hl, HID, K_LOGIN);
        xl += HID;
        KEEP(xl);
        hl += HID;
        KEEP(hl);
    }
    prepare(n, H, HID);                                           /* one input for the 6 blocks of logits */
    for (int b = 0; b < NVB; b++)                                 /* the logits, 8,192 columns at a time */
        product(n, mats + NL * 7 + b, 0, logits + (b << 13), VOC);
    i32 *lg = logits;
    site = S_OTHER;
    for (i64 l = 0; l < n; l++) {                                 /* greedy: the first largest */
        i64 best = 0, bv = lg[0];
        for (i64 i = 1; i < VOC; i++)
            if (lt(bv, lg[i])) {
                bv = lg[i];
                best = i;
            }
        next[l] = best;
        lg += VOC;
        KEEP(lg);
    }
    return 0;
}

#ifdef T3_HOST
int t3k_open(const char *blob, i64 slots, i64 positions, i64 threads) {
    fd = open(blob, O_RDONLY);
    if (fd < 0)
        return -100;
    return t3k_open_model(slots, positions, threads);
}
void t3k_counters(u64 *out) {
    const u64 *c = &t3k_cnt[0][0];
    for (int i = 0; i < NSITE << 3; i++)
        out[i] = c[i];
    out[NSITE << 3] = t3k_clamped;
    out[(NSITE << 3) + 1] = t3k_held;
    out[(NSITE << 3) + 2] = t3k_fail;
}
#endif
