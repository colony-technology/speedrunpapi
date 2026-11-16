# usage: python spare_row_test.py [f64|f32|i8]
# spare_row.Checked16 on synthetic operands (no model weights; the model's config.json only, for the head layout):
# locate() finds the place of a single error; the checked product and attention equal Exact16's; every single fault
# in a product sum, a weight, a product input (by the input sums) or a look is caught, and the repair gives back
# Exact16's output.
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exact_llm as X  # noqa: E402
import spare_row as S  # noqa: E402

route = sys.argv[1] if len(sys.argv) > 1 else "f64"
rng = np.random.default_rng(7)

# locate: e = 2^k u at place j
ok = 0
for _ in range(2000):
    n = int(rng.integers(1, 49153))
    j = int(rng.integers(1, n + 1))
    e = int(rng.integers(1, 1 << 40)) * (-1 if rng.random() < 0.5 else 1) << int(rng.integers(0, 20))
    ok += S.locate(e % S.M64, (j * e) % S.M64, n) == j
print("locate: %d of 2000 single errors placed" % ok)

m = object.__new__(S.Checked16)
S.install()
m.route, m.mmi = route, (X.MatMulInteger() if route == "i8" else None)
m.extra, m.p_held, m.spares, m.kstate, m._layer = 0, 0, {}, {}, 0
m.clamped, m.peak, m.layer_peak = {}, {}, {}
m.clamps = {"q": 1 << 7, "k": 1 << 7, "v": 1 << 12, "t": 1 << 7}
m.C = {k: v << X.A for k, v in m.clamps.items()}
m.Et = X.load_table("exp.txt")
nin, nout = 96, 300
w = rng.integers(-32767, 32768, size=(nin, nout)).astype(np.int16)
g = rng.integers(12, 17, size=nout).astype(np.int64)
m.W16 = {"t.weight": w, "t.weight.g": g}
x = rng.integers(-(1 << 22), 1 << 22, size=(5, nin)).astype(np.int64)

S.FX = S.Faults(survey=True)
y0 = m.product(m.prepare(x, "t"), "t.weight")
seen, widths = dict(S.FX.seen), dict(S.FX.top)
print("product: fault points %s, widths %s" % (seen, widths))
S.FX = S.Faults()
yref = X.Exact16.product(m, X.Exact16.prepare(m, x, "t"), "t.weight")
print("product: checked equals Exact16's:", bool((y0 == yref).all()), "; checks fired:", S.FX.fired)
for kind in ("sum", "weight", "input"):
    caught = rep = 0
    for _ in range(300):
        arm = (kind, int(rng.integers(seen[kind])), float(rng.random()))
        S.FX = S.Faults(arm, widths)
        try:
            m.product(m.prepare(x, "t"), "t.weight")
        except (AssertionError, IndexError, ValueError):
            pass                                  # the fault carried on stopped the run; whether a check saw it first:
        caught += bool(S.FX.fired)
        S.FX = S.Faults(arm, widths, repair=True)
        y = m.product(m.prepare(x, "t"), "t.weight")
        rep += bool((y == y0).all())
    print("product, %-6s faults: 300 injected, %d caught, %d give Exact16's output after repair" % (kind, caught, rep))

# attention: 135M head layout, batch 2, a prefill of 6 then one step
B, L = 2, 6
q = rng.integers(-(1 << 22), 1 << 22, size=(B, L, X.HEADS, X.HEAD)).astype(np.int64).transpose(0, 2, 1, 3)   # laid out as in the model: not C-contiguous
k = rng.integers(-(1 << 22), 1 << 22, size=(B, X.KV, L, X.HEAD)).astype(np.int64)
v = rng.integers(-(1 << 27), 1 << 27, size=(B, X.KV, L, X.HEAD)).astype(np.int64)
i = np.arange(L)
kvalid = np.broadcast_to(i[None, None, :] <= i[None, :, None], (B, L, L))
S.FX = S.Faults(survey=True)
m.kstate, m._layer = {}, 0
a0 = m.attention(q, *m.cache_entry(k, v), kvalid)
seen, widths = dict(S.FX.seen), dict(S.FX.top)
S.FX = S.Faults()
aref = X.Exact16.attention(m, q, *X.Exact16.cache_entry(m, k, v), kvalid)
print("attention: checked equals Exact16's:", bool((a0 == aref).all()), "; checks fired:", S.FX.fired)
for kind in ("sum", "input", "look"):
    caught = rep = 0
    for _ in range(300):
        arm = (kind, int(rng.integers(seen[kind])), float(rng.random()))
        for repair in (False, True):
            S.FX = S.Faults(arm, widths, repair)
            m.kstate, m._layer = {}, 0
            try:
                a = m.attention(q, *m.cache_entry(k, v), kvalid)
            except (AssertionError, IndexError, ValueError) as why:
                a = None
            if not repair:
                caught += bool(S.FX.fired) or a is None
            else:
                rep += a is not None and bool((a == a0).all())
    print("attention, %-4s faults: 300 injected, %d caught, %d give Exact16's output after repair" % (kind, caught, rep))
