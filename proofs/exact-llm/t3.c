/* t3.c: the t3 route of exact-16. Matrix products and element-wise products by add, subtract, shift by a constant
 * and bitwise logic; no multiply instruction (t3_nomul.py reads the compiled object and checks).
 *
 * Signed digits. For m >= 0: h = m >> 1, s = m + h, c = h ^ s, plus = s & c, minus = h & c; then m = plus - minus,
 * plus & minus = 0, and no two neighbouring positions are nonzero (the non-adjacent form, the fewest nonzero signed
 * digits). A negative value is recoded as its magnitude 0 - v with plus and minus exchanged. |v| <= 2^15 - 1 has its
 * digits at positions 0 to 15.
 *
 * The stream. A matrix W [n_in][M] (inputs by outputs) is compiled to 16-bit words, output row by output row; per
 * row, for digit position k = 15 down to 0: ADD i for each input whose weight has digit +1 at k, then SUB i for each
 * with -1 at k (i ascending), then STEP (k > 0) or EMIT (k = 0).
 *   word = op << 14 | i       op 0 ADD, 1 SUB, 2 STEP, 3 EMIT; i < 2^14
 * The machine. State: N lanes (one per input vector), each with s (int32) and acc (int64); x[i][lane] the inputs.
 *   ADD i   s = s + x[i]
 *   SUB i   s = s - x[i]
 *   STEP    acc = acc + acc; acc = acc + s; s = 0              (Horner over the digit positions: 2 adds)
 *   EMIT    STEP, then y[row] = acc; acc = 0; row = row + 1
 * So y[row] = sum_k 2^k (sum of x over digit +1 at k - sum over digit -1 at k) = sum_i W[i][row] x[i], exactly:
 * |s| <= n_in (2^15 - 1) < 2^31 for n_in < 2^16; after the STEP of position k, acc = sum_i x[i] (the digits of
 * W[i][row] at positions k..15, as a number), each such number below 2^16 in magnitude: |acc| < n_in 2^31 < 2^47.
 * The lanes run 8 at a time (N a multiple of 8, padded with zero inputs); the counters count the nreal lanes.
 *
 * Counters (uint64, added to, never reset here): cnt[0] digit adds and subtracts, lane by lane; cnt[1] Horner adds;
 * cnt[2] values recoded; cnt[3] recoding operations (shift, add, xor, and, and, plus a subtract for a negative).
 */
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>

#define OP_ADD 0u
#define OP_SUB 1u
#define OP_STEP 2u
#define OP_EMIT 3u
#define TOP 15
/* An empty barrier on a register: the compiler may not fold a loop of adds around it into a multiply. */
#define KEEP(v) __asm__ volatile("" : "+r"(v))

/* The signed digits of v (|v| < 2^62): *pl and *mi with v = *pl - *mi. Returns the operations used. */
static inline uint64_t recode(int64_t v, uint64_t *pl, uint64_t *mi) {
    uint64_t neg = v < 0;
    uint64_t m = neg ? (uint64_t)0 - (uint64_t)v : (uint64_t)v;
    uint64_t h = m >> 1, s = m + h, c = h ^ s;
    uint64_t p = s & c, q = h & c;
    *pl = neg ? q : p;
    *mi = neg ? p : q;
    return neg ? 6 : 5;
}

/* Pass 1. W int32 [n_in][M], row stride ld (elements). Writes the masks Pm, Mm [M][n_in] (16 bits each) and
 * rowoff[0..M] (word offsets of each row in the stream). Returns the stream length in words. */
int64_t t3_compile_masks(int64_t n_in, int64_t M, const int32_t *W, int64_t ld, uint16_t *Pm, uint16_t *Mm,
                         int64_t *rowoff, uint64_t *cnt) {
    const int32_t *wr = W;
    for (int64_t i = 0; i < n_in; i++) {
        uint16_t *pp = Pm + i, *mm = Mm + i;
        for (int64_t j = 0; j < M; j++) {
            uint64_t p, q;
            cnt[3] += recode(wr[j], &p, &q);
            cnt[2] += 1;
            *pp = (uint16_t)p;
            *mm = (uint16_t)q;
            pp += n_in;
            mm += n_in;
        }
        wr += ld;
    }
    int64_t off = 0;
    const uint16_t *pp = Pm, *mm = Mm;
    for (int64_t j = 0; j < M; j++) {
        rowoff[j] = off;
        off += TOP + 1;                                         /* the STEP and EMIT words */
        for (int64_t i = 0; i < n_in; i++) {
            uint32_t d = (uint32_t)pp[i] | (uint32_t)mm[i];
            while (d) {                                         /* one per nonzero digit */
                off += d & 1u;
                d >>= 1;
            }
        }
        pp += n_in;
        mm += n_in;
    }
    rowoff[M] = off;
    return off;
}

/* Pass 2: the words, from the masks. */
void t3_compile_fill(int64_t n_in, int64_t M, const uint16_t *Pm, const uint16_t *Mm, uint16_t *stream) {
    uint16_t *o = stream;
    const uint16_t *pp = Pm, *mm = Mm;
    for (int64_t j = 0; j < M; j++) {
        uint32_t bit = 1u << TOP;
        while (bit) {
            for (int64_t i = 0; i < n_in; i++)
                if (pp[i] & bit)
                    *o++ = (uint16_t)((OP_ADD << 14) | (uint32_t)i);
            for (int64_t i = 0; i < n_in; i++)
                if (mm[i] & bit)
                    *o++ = (uint16_t)((OP_SUB << 14) | (uint32_t)i);
            bit >>= 1;
            *o++ = (uint16_t)((bit ? OP_STEP : OP_EMIT) << 14);
        }
        pp += n_in;
        mm += n_in;
    }
}

/* The machine on rows [r0, r1) of a stream. x int32 [n_in][N]; y int64 [M][N]; N a multiple of 8. */
typedef struct {
    const uint16_t *stream;
    const int64_t *rowoff;
    int64_t r0, r1, n_in, N, nreal;
    const int32_t *x;
    int64_t *y;
    uint64_t cnt[4];
} job_t;

typedef int32_t v8 __attribute__((vector_size(32)));        /* 8 lanes of s */
typedef int64_t v8l __attribute__((vector_size(64)));       /* 8 lanes of acc */

static void *run_rows(void *arg) {
    job_t *jb = (job_t *)arg;
    int64_t N = jb->N;
    const int32_t **xrow = (const int32_t **)malloc(((size_t)jb->n_in + 1) * sizeof(*xrow));
    const int32_t *xp = jb->x;
    for (int64_t i = 0; i < jb->n_in; i++) {                 /* row addresses by repeated addition */
        xrow[i] = xp;
        xp += N;
        KEEP(xp);
    }
    int64_t *yrow = jb->y;
    for (int64_t r = 0; r < jb->r0; r++) {
        yrow += N;
        KEEP(yrow);                                             /* an add per row, not one multiply */
    }
    uint64_t adds = 0, horner = 0;
    for (int64_t r = jb->r0; r < jb->r1; r++) {
        const uint16_t *start = jb->stream + jb->rowoff[r];
        int64_t left = jb->nreal;                               /* real lanes not yet run */
        for (int64_t c = 0; c < N; c += 8) {                    /* the row's words once per 8 lanes */
            uint64_t nl = left < 8 ? (uint64_t)left : 8u;
            left -= 8;
            const uint16_t *p = start;
            v8 s = {0, 0, 0, 0, 0, 0, 0, 0};
            v8l acc = {0, 0, 0, 0, 0, 0, 0, 0};
            for (;;) {
                uint32_t w = *p++;
                uint32_t op = w >> 14;
                if (op == OP_ADD) {
                    v8 xv;
                    __builtin_memcpy(&xv, xrow[w & 0x3FFFu] + c, sizeof xv);
                    s += xv;
                    adds += nl;
                } else if (op == OP_SUB) {
                    v8 xv;
                    __builtin_memcpy(&xv, xrow[w & 0x3FFFu] + c, sizeof xv);
                    s -= xv;
                    adds += nl;
                } else {
                    acc = acc + acc;
                    acc = acc + __builtin_convertvector(s, v8l);
                    s = (v8){0, 0, 0, 0, 0, 0, 0, 0};
                    horner += nl;
                    horner += nl;
                    if (op == OP_EMIT)
                        break;
                }
            }
            __builtin_memcpy(yrow + c, &acc, sizeof acc);
        }
        yrow += N;
    }
    jb->cnt[0] = adds;
    jb->cnt[1] = horner;
    free(xrow);
    return NULL;
}

/* y [M][N] = W^T x for the compiled stream, rows split at part[0..nthreads] (part[0] = 0, part[nthreads] = M). */
void t3_run(const uint16_t *stream, const int64_t *rowoff, int64_t n_in, int64_t N, int64_t nreal, const int32_t *x, int64_t *y,
            int64_t nthreads, const int64_t *part, uint64_t *cnt) {
    job_t jobs[64];
    pthread_t th[64];
    if (nthreads > 64)
        nthreads = 64;
    for (int64_t t = 0; t < nthreads; t++) {
        job_t *jb = &jobs[t];
        jb->stream = stream;
        jb->rowoff = rowoff;
        jb->r0 = part[t];
        jb->r1 = part[t + 1];
        jb->n_in = n_in;
        jb->N = N;
        jb->nreal = nreal;
        jb->x = x;
        jb->y = y;
        if (nthreads == 1)
            run_rows(jb);
        else
            pthread_create(&th[t], NULL, run_rows, jb);
    }
    for (int64_t t = 0; t < nthreads; t++) {
        if (nthreads > 1)
            pthread_join(th[t], NULL);
        cnt[0] += jobs[t].cnt[0];
        cnt[1] += jobs[t].cnt[1];
    }
}

/* out[e] = a[e] b[e] for n elements, b recoded at run time (|b| < 2^62, its digits at positions 0..K, top = 2^K):
 * Horner from position K down: acc = acc + acc, then + a at a digit +1, - a at a digit -1. Arithmetic mod 2^64, as
 * NumPy's int64 product. */
void t3_mul(int64_t n, const int64_t *a, const int64_t *b, int64_t *out, uint64_t top, uint64_t *cnt) {
    uint64_t adds = 0, horner = 0, ops = 0;
    for (int64_t e = 0; e < n; e++) {
        uint64_t pl, mi;
        ops += recode(b[e], &pl, &mi);
        uint64_t x = (uint64_t)a[e], acc = 0, bit = top;
        while (bit) {
            acc = acc + acc;
            horner += 1;
            KEEP(horner);
            if (pl & bit) {
                acc = acc + x;
                adds += 1;
            }
            if (mi & bit) {
                acc = acc - x;
                adds += 1;
            }
            bit >>= 1;
        }
        out[e] = (int64_t)acc;
    }
    cnt[0] += adds;
    cnt[1] += horner;
    cnt[2] += (uint64_t)n;
    cnt[3] += ops;
}
