// Five dials: every unit set of five moduli, all below B, with largest / smallest <= R.
// As search4.c: with every modulus >= 6 the signed fractions sum to less than one turn (5/6 < 1), so a unit set
// satisfies sum_i e_i M/m_i = s, s = +-1. For the four smallest v < w < x < y and the signs, the fifth is
//   z = (s - e_z v w x y) / (e_v w x y + e_w v x y + e_x v w y + e_y v w x)   (e_v = +1).
// Every candidate is checked against the definition. Sets with a modulus below 6 (all moduli below 6R) by brute force.
// usage: search5 B R
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

typedef __int128 i128;
static long gcdl(long a, long b) { while (b) { long t = a % b; a = b; b = t; } return a; }
static int unit(const long *m, int k, int *sg) {
    for (int i = 0; i < k; i++) for (int j = i + 1; j < k; j++) if (gcdl(m[i], m[j]) != 1) return 0;
    for (int i = 0; i < k; i++) {
        i128 p = 1;
        for (int j = 0; j < k; j++) if (j != i) p = (p * m[j]) % m[i];
        long r = (long)p;
        if (r == 1 % m[i]) sg[i] = 1; else if (r == m[i] - 1) sg[i] = -1; else return 0;
    }
    return 1;
}
#define HN (1 << 22)
static long hk[HN][5]; static char hu[HN];
static int seen(const long *m) {
    uint64_t h = 1469598103934665603ull;
    for (int i = 0; i < 5; i++) { h ^= (uint64_t)m[i]; h *= 1099511628211ull; }
    uint64_t i = h & (HN - 1);
    while (hu[i]) {
        int eq = 1; for (int k = 0; k < 5; k++) if (hk[i][k] != m[k]) eq = 0;
        if (eq) return 1;
        i = (i + 1) & (HN - 1);
    }
    hu[i] = 1; for (int k = 0; k < 5; k++) hk[i][k] = m[k];
    return 0;
}
static long found = 0;
static void report(const long *in, double R) {
    long m[5]; for (int i = 0; i < 5; i++) m[i] = in[i];
    for (int i = 0; i < 5; i++) for (int j = i + 1; j < 5; j++) if (m[j] < m[i]) { long t = m[i]; m[i] = m[j]; m[j] = t; }
    for (int i = 0; i < 4; i++) if (m[i] == m[i + 1]) return;
    if (m[0] < 2 || (double)m[4] > R * (double)m[0]) return;
    int sg[5];
    if (!unit(m, 5, sg)) return;
    if (seen(m)) return;
    found++;
    printf("%ld %ld %ld %ld %ld %+d %+d %+d %+d %+d\n", m[0], m[1], m[2], m[3], m[4], sg[0], sg[1], sg[2], sg[3], sg[4]);
}
int main(int argc, char **argv) {
    const long B = atol(argv[1]); const double R = atof(argv[2]);
    long cand = 0;
    const long Bs = (long)(6 * R) + 1 < B ? (long)(6 * R) + 1 : B;
    for (long a = 2; a < 6; a++) for (long b = a + 1; b < Bs; b++) for (long c = b + 1; c < Bs; c++)
        for (long d = c + 1; d < Bs; d++) for (long e = d + 1; e < Bs; e++) { long m[5] = {a, b, c, d, e}; report(m, R); }
    for (long v = 6; v < B; v++) {
        const long top = (long)(R * v) < B - 1 ? (long)(R * v) : B - 1;
        for (long w = v + 1; w <= top; w++) {
            if (gcdl(v, w) != 1) continue;
            for (long x = w + 1; x <= top; x++) {
                if (gcdl(v, x) != 1 || gcdl(w, x) != 1) continue;
                for (long y = x + 1; y <= top; y++) {
                    if (gcdl(v, y) != 1 || gcdl(w, y) != 1 || gcdl(x, y) != 1) continue;
                    const i128 P4 = (i128)v * w * x * y;
                    const i128 a0 = (i128)w * x * y, a1 = (i128)v * x * y, a2 = (i128)v * w * y, a3 = (i128)v * w * x;
                    for (int ew = -1; ew <= 1; ew += 2) for (int ex = -1; ex <= 1; ex += 2) for (int ey = -1; ey <= 1; ey += 2)
                    for (int ez = -1; ez <= 1; ez += 2) for (int s = -1; s <= 1; s += 2) {
                        const i128 T = a0 + ew * a1 + ex * a2 + ey * a3;
                        if (T == 0) continue;
                        const i128 num = (i128)s - (i128)ez * P4;
                        if (num % T != 0) continue;
                        const i128 z = num / T;
                        if (z < 2 || z >= B) continue;
                        cand++;
                        long m[5] = {v, w, x, y, (long)z}; report(m, R);
                    }
                }
            }
        }
    }
    fprintf(stderr, "B=%ld R=%g: candidates %ld, unit sets of five %ld\n", B, R, cand, found);
    return 0;
}
