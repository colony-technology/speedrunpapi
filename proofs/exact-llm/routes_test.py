# usage: python routes_test.py
# mm16 on its three routes against exact int64 products: random and extreme 16-bit operands, 2-D and the batched
# shapes the attention uses, widths across the f32 chunk edge (1,024) and up to 1,536.
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exact_llm as X  # noqa: E402

rng = np.random.default_rng(7)
L = X.LIM16
mmi = X.MatMulInteger()
print("i8 product engine:", mmi.name)
shapes = [((5, 576), (576, 300)), ((3, 1023), (1023, 7)), ((3, 1024), (1024, 7)), ((3, 1025), (1025, 7)),
          ((4, 1536), (1536, 64)), ((2, 3, 27, 64), (2, 3, 64, 40)), ((2, 3, 27, 600), (2, 3, 600, 64))]
bad = 0
for sa, sb in shapes:
    for kind in ("random", "all +max", "all -max", "+max by -max", "p-like"):
        if kind == "random":
            a, b = rng.integers(-L, L + 1, sa), rng.integers(-L, L + 1, sb)
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
        for r in X.ROUTES:
            for bb in (b, b.astype(np.int16)):                         # the weights come as int16
                y = X.mm16(a, bb, r, mmi)
                if y.dtype != np.int64 or y.shape != ref.shape or not (y == ref).all():
                    bad += 1
                    print("DIFFERENT", r, sa, sb, kind, bb.dtype)
print("cases %d (int64 and int16 right operands), routes %d, different %d" % (len(shapes) * 5, len(X.ROUTES), bad))
# the byte digits stay inside the stated ranges
a = np.arange(-L, L + 1, dtype=np.int64)
h = (a + 128) >> 8
lo = a - (h << 8)
a16 = a.astype(np.int16)                               # the split as mm16 does it on int16 weights, without widening
lo16 = ((a16 & 255) ^ 128) - 128
h16 = (a16 >> 8) + (lo16 < 0)
same = (h16 == h).all() and (lo16 == lo).all() and ((h16.astype(np.int64) << 8) + lo16 == a).all()
bad += 0 if same else 1
print("f32 digits: high %d..%d, low %d..%d (int16 split the same: %s); i8 digits: high %d..%d, low %d..%d" % (
    h.min(), h.max(), lo.min(), lo.max(), same, (a >> 8).min(), (a >> 8).max(), (a & 255).min(), (a & 255).max()))
# peel_index: ties go to the lower index
x = np.array([[5, -9, 9, 3, -9, 1]], dtype=np.int64)
print("peel_index of", x.tolist()[0], "k=2:", sorted(X.peel_index(x, 2)[0].tolist()), "(expect [1, 2])")
sys.exit(1 if bad else 0)
