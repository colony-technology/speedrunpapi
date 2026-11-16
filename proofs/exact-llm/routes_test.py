# usage: python routes_test.py
# mm16 on its three routes against exact int64 products: random and extreme 16-bit operands, 2-D and the batched
# shapes the attention uses, widths across the f32 chunk edge (1,024) and up to 1,536.
# The worst cases for what a kernel holds inside: "all +max" puts every byte digit of the i8 route at 255 in every
# position (each byte product 255^2, the largest pair sum 2 x 255^2 = 130,050, which needs 32 bits), and the f32
# route's top digits at 128 (a chunk of 1,024 sums to exactly 2^24, the float32 edge). "+max by -max" is the same
# with the products negative. "digit extremes" mixes, position by position, the eight values whose digits sit at the
# ends of both routes' digit ranges. A kernel that saturates or rounds anywhere fails one of these.
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exact_llm as X  # noqa: E402

rng = np.random.default_rng(7)
L = X.LIM16
mmi = X.MatMulInteger()
print("i8 product engine:", mmi.name)
# t3 (t3.c, by adds and subtracts) where a C compiler is installed, not on Windows
T3 = X.t3_missing() is None
ROUTES = X.ROUTES + (X.ROUTES_T3 if T3 else ())
print("t3 kernel:", X.t3_kernel().path if T3 else X.t3_missing() + ": not tested")
shapes = [((5, 576), (576, 300)), ((3, 1023), (1023, 7)), ((3, 1024), (1024, 7)), ((3, 1025), (1025, 7)),
          ((4, 1536), (1536, 64)), ((2, 3, 27, 64), (2, 3, 64, 40)), ((2, 3, 27, 600), (2, 3, 600, 64))]
# digits (i8: of a + 2^15, high and low; f32: balanced high and low): 32767 (255, 255; 128, -1), -32767 (0, 1;
# -128, 1), 32640 (255, 128; 128, -128), -32640 (0, 128; -127, -128), 32639 (255, 127; 127, 127), -32641 (0, 127;
# -128, 127), 32512 (255, 0; 127, 0), -32513 (0, 255; -127, -1)
EXTREMES = np.array([32767, -32767, 32640, -32640, 32639, -32641, 32512, -32513])
KINDS = ("random", "all +max", "all -max", "+max by -max", "p-like", "digit extremes")
bad = 0
for sa, sb in shapes:
    for kind in KINDS:
        if kind == "random":
            a, b = rng.integers(-L, L + 1, sa), rng.integers(-L, L + 1, sb)
        elif kind == "digit extremes":
            a, b = rng.choice(EXTREMES, sa), rng.choice(EXTREMES, sb)
        elif kind == "all +max":
            a, b = np.full(sa, L), np.full(sb, L)
        elif kind == "all -max":
            a, b = np.full(sa, -L), np.full(sb, -L)
        elif kind == "+max by -max":
            a, b = np.full(sa, L), np.full(sb, -L)
        else:
            a, b = rng.integers(0, L + 1, sa), rng.integers(-L, L + 1, sb)
        a, b = a.astype(np.int64), b.astype(np.int64)
        ref = np.matmul(a, b)                                          # int64, exact: |sum| < 1536 * 2^30
        for r in ROUTES:
            for bb in (b, b.astype(np.int16)):                         # the weights come as int16
                y = X.mm16(a, bb, r, mmi)
                if y.dtype != np.int64 or y.shape != ref.shape or not (y == ref).all():
                    bad += 1
                    print("DIFFERENT", r, sa, sb, kind, bb.dtype)
print("cases %d (%d shapes x %d kinds, int64 and int16 right operands), routes %d, different %d" % (
    len(shapes) * len(KINDS), len(shapes), len(KINDS), len(ROUTES), bad))
# the extremes have the digits stated above
u = EXTREMES + (1 << 15)
h = (EXTREMES + 128) >> 8
ok = [(int(x), (int(p) >> 8, int(p) & 255), (int(q), int(x - (q << 8)))) for x, p, q in zip(EXTREMES, u, h)]
print("digit extremes, value (i8 digits) (f32 digits):", "; ".join("%d %s %s" % t for t in ok))
# the byte digits stay inside the stated ranges
a = np.arange(-L, L + 1, dtype=np.int64)
h = (a + 128) >> 8
lo = a - (h << 8)
a16 = a.astype(np.int16)                               # the split as mm16 does it on int16 weights, without widening
lo16 = ((a16 & 255) ^ 128) - 128
h16 = (a16 >> 8) + (lo16 < 0)
same = (h16 == h).all() and (lo16 == lo).all() and ((h16.astype(np.int64) << 8) + lo16 == a).all()
u16 = a16.view(np.uint16) ^ 0x8000                      # the i8 route's u = a + 2^15, from int16 without widening
same_u = (u16.astype(np.int64) == a + (1 << 15)).all()
bad += 0 if same and same_u else 1
u = a + (1 << 15)
print("f32 digits: high %d..%d, low %d..%d (int16 split the same: %s); i8 digits of a + 2^15: high %d..%d, "
      "low %d..%d (from int16 the same: %s)" % (h.min(), h.max(), lo.min(), lo.max(), same, (u >> 8).min(),
                                               (u >> 8).max(), (u & 255).min(), (u & 255).max(), same_u))
# peel_index: ties go to the lower index
x = np.array([[5, -9, 9, 3, -9, 1]], dtype=np.int64)
print("peel_index of", x.tolist()[0], "k=2:", sorted(X.peel_index(x, 2)[0].tolist()), "(expect [1, 2])")
if T3:
    k3 = X.t3_kernel()
    # every 16-bit value through the stream: y = 1 . b for b = -32767 .. 32767, one input, 65,535 output rows; then
    # the digits as the kernel forms them: nonzero digits per value against the census formula, popcount(h ^ (m + h))
    v = np.arange(-L, L + 1, dtype=np.int64)
    y = k3.mm(np.ones((1, 1), np.int64), v[None])
    m = np.abs(v)
    naf = np.bitwise_count(((m >> 1) ^ (m + (m >> 1))).astype(np.uint64)).astype(np.int64)
    before = k3.cnt["attention"].copy()
    k3.mm(np.ones((1, 1), np.int64), v[None])
    adds = int(k3.cnt["attention"][0] - before[0])
    ok3 = (y[0] == v).all() and adds == int(naf.sum())
    bad += 0 if ok3 else 1
    print("t3 stream, every value -32767..32767: %s; digit adds %d, census formula %d, at most %d per value" % (
        "exact" if (y[0] == v).all() else "DIFFERENT", adds, int(naf.sum()), int(naf.max())))
    # element-wise: random int64 pairs whose product fits, the extremes, and signs
    a = rng.integers(-(1 << 31), 1 << 31, 200000)
    b = rng.integers(-(1 << 31), 1 << 31, 200000)
    e = np.array([0, 1, -1, L, -L, (1 << 31) - 1, -(1 << 31), (1 << 40) + 3, -(1 << 41) - 5])
    a, b = np.concatenate([a, np.repeat(e, e.size)]), np.concatenate([b, np.tile(e[::-1], e.size)])
    okm = (k3.mul(a, b) == a * b).all() and (k3.mul(b[:, None], a[None, :50]) == b[:, None] * a[None, :50]).all()
    bad += 0 if okm else 1
    print("t3 element-wise products, %d pairs and a broadcast: %s" % (a.size, "exact" if okm else "DIFFERENT"))
sys.exit(1 if bad else 0)
