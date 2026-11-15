// Every unit set of four moduli, all below B, with largest / smallest <= R.
// A unit set with signs e satisfies sum_i e_i M/m_i = 1 (mod M) (claim 1). When every modulus is at least 6 the
// fractions sum to less than one turn in absolute value, so the congruence is the equality
//   sum_i e_i M/m_i = s,  s = +1 or -1   (e and s up to a common sign).
// For w < x < y the smallest three, and signs (e_w, e_x, e_y, e_z), s: z (e_w x y + e_x w y + e_y w x) = s - e_z w x y,
// so z is determined. Every candidate is checked against the definition (M/m_i = +-1 mod m_i, pairwise coprime).
// Sets with a modulus below 6 have every modulus below 6R and are searched by brute force over all quadruples.
// Output: one line per set (sorted moduli, signs of M/m_i mod m_i), to stdout; counts to stderr.
// usage: search4 B R
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
static long hk[HN][4]; static char hu[HN];
static int seen(const long *m) {                     // insert into a hash set; 1 if already there
    uint64_t h = 1469598103934665603ull;
    for (int i = 0; i < 4; i++) { h ^= (uint64_t)m[i]; h *= 1099511628211ull; }
    uint64_t i = h & (HN - 1);
    while (hu[i]) {
        if (hk[i][0] == m[0] && hk[i][1] == m[1] && hk[i][2] == m[2] && hk[i][3] == m[3]) return 1;
        i = (i + 1) & (HN - 1);
    }
    hu[i] = 1; for (int k = 0; k < 4; k++) hk[i][k] = m[k];
    return 0;
}
static long found = 0;
static void report(long a, long b, long c, long d, double R) {
    long m[4] = {a, b, c, d};
    for (int i = 0; i < 4; i++) for (int j = i + 1; j < 4; j++) if (m[j] < m[i]) { long t = m[i]; m[i] = m[j]; m[j] = t; }
    if (m[0] == m[1] || m[1] == m[2] || m[2] == m[3] || m[0] < 2) return;
    if ((double)m[3] > R * (double)m[0]) return;
    int sg[4];
    if (!unit(m, 4, sg)) return;
    if (seen(m)) return;
    found++;
    printf("%ld %ld %ld %ld %+d %+d %+d %+d\n", m[0], m[1], m[2], m[3], sg[0], sg[1], sg[2], sg[3]);
}
int main(int argc, char **argv) {
    const long B = atol(argv[1]); const double R = atof(argv[2]);
    long cand = 0;
    // brute force where a modulus is below 6
    const long Bs = (long)(6 * R) + 1;
    for (long a = 2; a < 6; a++) for (long b = a + 1; b < Bs && b < B; b++) for (long c = b + 1; c < Bs && c < B; c++)
        for (long d = c + 1; d < Bs && d < B; d++) report(a, b, c, d, R);
    // the equation for the rest
    for (long w = 6; w < B; w++) {
        const long top = (long)(R * w) < B - 1 ? (long)(R * w) : B - 1;
        for (long x = w + 1; x <= top; x++) {
            if (gcdl(w, x) != 1) continue;
            for (long y = x + 1; y <= top; y++) {
                if (gcdl(w, y) != 1 || gcdl(x, y) != 1) continue;
                const i128 wxy = (i128)w * x * y;
                for (int ex = -1; ex <= 1; ex += 2) for (int ey = -1; ey <= 1; ey += 2) for (int ez = -1; ez <= 1; ez += 2)
                for (int s = -1; s <= 1; s += 2) {
                    const i128 T = (i128)x * y + (i128)ex * w * y + (i128)ey * w * x;      // e_w = +1
                    if (T == 0) continue;
                    const i128 num = (i128)s - (i128)ez * wxy;
                    if (num % T != 0) continue;
                    const i128 z = num / T;
                    if (z < 2 || z >= B || z == w || z == x || z == y) continue;
                    cand++;
                    report(w, x, y, (long)z, R);
                }
            }
        }
    }
    fprintf(stderr, "B=%ld R=%g: candidates %ld, unit sets of four %ld\n", B, R, cand, found);
    return 0;
}
