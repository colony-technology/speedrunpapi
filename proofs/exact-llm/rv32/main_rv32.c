/* main_rv32.c: t3_token.c freestanding on rv32i (QEMU virt, bare metal). Reads the model blob (t3k.blob) and the
 * token ids (tokens.bin: int64 count, then the ids) through semihosting from QEMU's working directory, runs the
 * tokens at positions 0, 1, ..., and prints over the UART (ns16550 at 0x10000000), per position:
 *   pos P sha256 <logits, int32 little-endian, 49,152> instret <instructions for the step, hex> next <token, hex>
 * The instruction count is the difference of rdinstret around t3k_step (exact under QEMU -icount). No multiply,
 * no divide, no libc. */
#include <stdint.h>

typedef int64_t i64;
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;

extern int t3k_open_model(i64 slots, i64 positions, i64 threads);
extern int t3k_step(i64 n, const i64 *slots, const i64 *tok, const i64 *pos, int32_t *logits, i64 *next);
extern void t3k_arena(void *base, u64 size);
extern long t3_semihost(long op, void *arg);
extern char __bss_start[], __bss_end[], __arena_start[], __arena_end[];

#define VOC 49152

void *memset(void *d, int c, unsigned long n) {
    volatile u8 *p = (volatile u8 *)d;
    while (n) {
        *p++ = (u8)c;
        n -= 1;
    }
    return d;
}
void *memcpy(void *d, const void *s, unsigned long n) {
    volatile u8 *p = (volatile u8 *)d;
    const volatile u8 *q = (const volatile u8 *)s;
    while (n) {
        *p++ = *q++;
        n -= 1;
    }
    return d;
}

/* ---- UART ---- */
static void putc_(char c) {
    volatile u8 *u = (volatile u8 *)0x10000000;
    while (!(u[5] & 0x20))
        ;
    u[0] = (u8)c;
}
static void puts_(const char *s) {
    while (*s)
        putc_(*s++);
}
static void puthex(u64 v, int digits) {
    for (int i = digits - 1; i >= 0; i--) {
        u32 d = (u32)(v >> (i << 2)) & 15u;
        putc_((char)(d < 10 ? '0' + d : 'a' + d - 10));
    }
}

/* ---- semihosting files ---- */
static long sh_open(const char *name) {
    long len = 0;
    while (name[len])
        len += 1;
    long a[3] = {(long)name, 1, len};                     /* mode 1: "rb" */
    return t3_semihost(0x01, a);
}
static long blob = -1;
int t3_io_read(u64 off, void *dst, u64 n) {
    if (off >> 31)
        return -1;
    long s[2] = {blob, (long)off};
    if (t3_semihost(0x0A, s) != 0)                        /* SYS_SEEK */
        return -1;
    u8 *d = (u8 *)dst;
    while (n) {
        u32 part = n > 0x1000000u ? 0x1000000u : (u32)n;
        long r[3] = {blob, (long)d, (long)part};
        if (t3_semihost(0x06, r) != 0)                    /* SYS_READ: bytes not read */
            return -1;
        d += part;
        n -= part;
    }
    return 0;
}

/* ---- instructions retired ---- */
static u64 instret(void) {
    u32 hi, lo, hi2;
    do {
        __asm__ volatile("rdinstreth %0" : "=r"(hi));
        __asm__ volatile("rdinstret %0" : "=r"(lo));
        __asm__ volatile("rdinstreth %0" : "=r"(hi2));
    } while (hi != hi2);
    return ((u64)hi << 32) | lo;
}

/* ---- SHA-256 (adds, rotations, logic) ---- */
static const u32 K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
static void sha_block(u32 *h, const u8 *p) {
    u32 w[64];
    for (int i = 0; i < 16; i++) {
        w[i] = ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3];
        p += 4;
    }
    for (int i = 16; i < 64; i++) {
        u32 s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
        u32 s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    u32 a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
    for (int i = 0; i < 64; i++) {
        u32 t1 = k + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
        u32 t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
        k = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += k;
}
static void sha256(const u8 *m, u32 n, u32 *h) {             /* n a multiple of 64 here (196,608 bytes) */
    static const u32 H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                              0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    for (int i = 0; i < 8; i++)
        h[i] = H0[i];
    u32 left = n;
    while (left >= 64) {
        sha_block(h, m);
        m += 64;
        left -= 64;
    }
    u8 pad[64];
    for (int i = 0; i < 64; i++)
        pad[i] = 0;
    pad[0] = 0x80;
    u64 bits = (u64)n << 3;
    for (int i = 0; i < 8; i++)
        pad[63 - i] = (u8)(bits >> (i << 3));
    sha_block(h, pad);
}

static int32_t logits[VOC];

int main(void) {
    for (volatile char *p = __bss_start; p < __bss_end; p++)
        *p = 0;
    puts_("t3 rv32i: open\n");
    blob = sh_open("t3k.blob");
    long tf = sh_open("tokens.bin");
    if (blob < 0 || tf < 0) {
        puts_("t3 rv32i: cannot open t3k.blob or tokens.bin\n");
        return 1;
    }
    i64 tok[64], ntok = 0;
    long r0[3] = {tf, (long)&ntok, 8};
    if (t3_semihost(0x06, r0) != 0 || ntok < 1 || ntok > 64)
        return 2;
    long r1[3] = {tf, (long)tok, (long)(ntok << 3)};
    if (t3_semihost(0x06, r1) != 0)
        return 3;
    t3k_arena(__arena_start, (u64)(__arena_end - __arena_start));
    int e = t3k_open_model(1, 64, 1);
    if (e) {
        puts_("t3 rv32i: open_model failed ");
        puthex((u64)(i64)e, 8);
        puts_("\n");
        return 4;
    }
    puts_("t3 rv32i: model open, tokens ");
    puthex((u64)ntok, 2);
    puts_("\n");
    for (i64 t = 0; t < ntok; t++) {
        i64 slot = 0, pos = t, next = 0;
        u64 c0 = instret();
        t3k_step(1, &slot, &tok[t], &pos, logits, &next);
        u64 c1 = instret();
        u32 h[8];
        sha256((const u8 *)logits, VOC << 2, h);
        puts_("pos ");
        puthex((u64)t, 2);
        puts_(" sha256 ");
        for (int i = 0; i < 8; i++)
            puthex(h[i], 8);
        puts_(" instret ");
        puthex(c1 - c0, 16);
        puts_(" next ");
        puthex((u64)next, 8);
        puts_("\n");
    }
    puts_("t3 rv32i: done\n");
    return 0;
}
