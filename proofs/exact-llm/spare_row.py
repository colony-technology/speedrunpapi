"""The spare row on the exact-16 path (exact_llm.Exact16): every product checked by two spare rows of its weights, a
single wrong output located and computed again, the looks bracketed or made twice; and a fault campaign on the
real model.

In exact integers a product T = x W (the unrounded int64 sums) obeys, for each row of x,
    sum_j T_j   = x . c1,   c1_i = sum_j W_ij                 (the spare row)
    sum_j j T_j = x . c2,   c2_i = sum_j j W_ij, j = 1 .. n   (the second spare row)
with no tolerance. The checks run in int64 with wrap-around, that is modulo 2^64, at no cost: an error e is missed
only if 2^64 divides it, which no single fault below can do. A single wrong output j gives e1 = e and e2 = j e;
with e = 2^k u, u odd, j = (e2 / 2^k) u^-1 modulo 2^(64 - k), unique while n < 2^(64 - k). That output is then
computed again from the stored weights and rounded.

Products checked: q, k, v, o, gate, up, down and the logits (the 16-bit weights; the spare rows made once from the
stored weights); the scores q . k over the keys, with the two sums of the keys kept beside the cache (64 adds each
per new key); the context p . vh and p . vl over the 64 values, with the two sums of each v kept in the cache.

Inputs: the spare rows cannot see an input read wrongly, since the product and its rows read the same wrong value.
So the sum of each input vector travels from the look that makes it, and the product that reads the vector forms
the same sum as one more row of ones and compares; a wrong read is read again. For a product over the weights the
vector is made once by Exact16.prepare for every product that reads it (h for q, k and v; h for gate and up), and
the sum covers every word the product reads for a row: the 16-bit values, the peeled values and their places, the
shift. For the scores it is q as clamped; for the context, p as held.

Placing: the one case caught and not placed is a wrong bit so high that n 2^k reaches 2^64 (with n outputs, k the
lowest set bit of the error); the check fires, the row is left as it is.

Looks: rounding, bit length, division and square root by their brackets (y 2^k - 2^(k-1) <= v < y 2^k + 2^(k-1);
2^(b-1) <= a < 2^b; q d <= n < (q + 1) d; s^2 <= n < (s + 1)^2); the split of v by putting it back together
(v = 2^15 vh + vl); clamps, the held p, the table reads (exp, SiLU, cos and sin), the peel selection and the softmax
maximum made twice and compared.

usage:
  python spare_row.py hash --route f64|f32|i8 [--plain]   the 64 prompts at batch 8, every check on (--plain: none)
  python spare_row.py campaign [--n 100] [--seed 1] [--route f64] [--save FILE]
                                                          single faults of four kinds, one prompt and 4 tokens
"""
import collections
import hashlib
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

M64 = 1 << 64
KINDS = ("sum", "weight", "input", "look")
KIND_TEXT = {"sum": "one bit of one product sum", "weight": "one bit of one weight as it is read",
             "input": "one bit of one product input as it is read", "look": "one bit of the result of one look"}


class Faults:
    """The fault points and the checks of a run. Each fault point hands its array to point(kind, site, a); with a
    fault armed at element k of that kind (counted over the run, in the order the points are reached), one bit of
    that element is flipped, at a place drawn from u in [0, 1) times the site's width (the largest bit length seen
    there in the clean run; 16 for a weight). A check that fails is recorded; with repair on, the caller puts the
    value right."""

    def __init__(self, armed=None, widths=None, repair=False, survey=False):
        self.armed = armed                     # (kind, k, u) or None
        self.widths = widths or {}             # (kind, site) -> bits
        self.repair = repair
        self.survey = survey                   # the clean run of a campaign: record each site's largest bit length
        self.seen = collections.Counter()      # elements per kind
        self.top = {}                          # (kind, site) -> largest bit length seen
        self.hit = None
        self.fired = []                        # (check, site, rows)
        self.checks = collections.Counter()    # checks made, per check
        self.repaired = 0

    def point(self, kind, site, a):
        a = np.asanyarray(a)
        n = a.size
        c = self.seen[kind]
        self.seen[kind] = c + n
        if self.armed is None:
            if self.survey and kind != "weight" and n and a.dtype.kind in "iu":
                b = int(np.abs(a.astype(np.int64)).max()).bit_length()
                key = (kind, site)
                self.top[key] = max(self.top.get(key, 0), b)
            return a
        k_kind, k, u = self.armed
        if k_kind != kind or self.hit is not None or not (c <= k < c + n):
            return a
        width = 16 if kind == "weight" else max(1, self.widths.get((kind, site), 1))
        bit = min(width - 1, int(u * width))
        out = np.array(a, copy=True, order="C")             # C order, so that flat is a view and the flip lands
        flat = out.reshape(-1)
        i = k - c
        old = int(flat[i])
        if flat.dtype == np.int16:
            flat.view(np.uint16)[i] ^= np.uint16(1 << bit)
        else:
            flat[i] = flat[i] ^ flat.dtype.type(1 << bit)
        self.hit = {"kind": kind, "site": site, "bit": bit, "width": width, "old": old, "new": int(flat[i])}
        return out

    def check(self, name, ok, site):
        """Record a check over an array of booleans; returns the failing positions."""
        self.checks[name] += 1
        bad = ~np.asanyarray(ok)
        if bad.any():
            self.fired.append((name, site, int(bad.sum())))
        return bad


FX = Faults()                                  # the run's fault state; the campaign sets it before each run


# ---- the arithmetic of the checks, one kind of work per function (count_spare.py counts them by name) --------------
def two_sums(a, w, axis=-1):
    """The output side of the two spare rows: sum a and sum w a over an axis (w = 1 .. n)."""
    with np.errstate(over="ignore"):
        s1 = a.sum(axis)
        s2 = (a * w).sum(axis)
    return s1, s2


def spare_product(xb, sh, xp, idx, c):
    """The input side of a spare row for a product as Exact16 makes it: 2^sh (x16 . c) + the peeled x c."""
    with np.errstate(over="ignore"):
        lead = np.left_shift(xb @ c, sh[:, 0])
        peel = (xp * c[idx]).sum(axis=1)
        return lead + peel


def spare_dot(a, c):
    """The input side of a spare row over the last axis: a . c (scores against the key sums, context against the
    sums of each v)."""
    with np.errstate(over="ignore"):
        return (a * c).sum(-1)


def vector_sum(x):
    """The sum of each vector over its last axis: made where the vector is made (the look that makes it), and
    formed again by each product that reads it, as one more row of ones."""
    with np.errstate(over="ignore"):
        return x.sum(-1)


def read_input(name, x, made):
    """A product's read of its input vectors x: the fault point, then the sum of what was read against the sum that
    travelled from the look that made them. A wrong read is read again."""
    xr = FX.point("input", name, x)
    bad = FX.check("input sum", vector_sum(xr) == made, name)
    if bad.any() and FX.repair:
        FX.repaired += 1
        return x
    return xr


def rows_check(name, site, S1, S2, E1, E2):
    """The two spare rows of a product, per row: returns the failing rows."""
    return FX.check(name, (S1 == E1) & (S2 == E2), site)


def in_range(lo, v, hi):
    """A bracket: lo <= v < hi, one range test per value."""
    return (lo <= v) & (v < hi)


def twice(name, site, a1, a2):
    """A look made twice: a1 (through the fault point) against a2."""
    a1 = FX.point("look", site, a1)
    bad = FX.check(name, a1 == a2, site)
    if bad.any() and FX.repair:
        FX.repaired += 1
        return a2
    return a1


def locate(e1, e2, n):
    """The place j (1 .. n) of a single wrong output from the two row errors modulo 2^64, or None."""
    e1, e2 = int(e1) % M64, int(e2) % M64
    if e1 == 0:
        return None
    k = (e1 & -e1).bit_length() - 1
    if e2 % (1 << k) or 64 - k < n.bit_length():                         # unique while n < 2^(64 - k)
        return None
    m = 1 << (64 - k)
    j = ((e2 >> k) * pow(e1 >> k, -1, m)) % m
    return j if 1 <= j <= n else None


# ---- the looks, bracketed or made twice (installed over exact_llm's functions by install()) -------------------------
ORIG = {}


def _round(v, k, f):
    y = ORIG[f](v, k)
    y = FX.point("look", "rounding", y)
    kk = np.asanyarray(k, dtype=np.int64)
    half = np.left_shift(np.int64(1), kk) >> 1
    base = np.left_shift(y, kk)
    bad = FX.check("rounding bracket", in_range(base - half, v, base + np.maximum(half, 1)), "rounding")
    if bad.any() and FX.repair:
        y = ORIG[f](v, k)
        FX.repaired += 1
    return y


def shift_round(v, k):
    return _round(v, k, "shift_round")


def rshift_round(v, k):
    return _round(v, k, "rshift_round") if k > 0 else v


def bitlen(a):
    b = ORIG["bitlen"](a)
    b = FX.point("look", "bit length", b)
    hi = np.left_shift(np.int64(1), b)
    bad = FX.check("bit length bracket", in_range(hi >> 1, np.asanyarray(a, dtype=np.int64), hi), "bit length")
    if bad.any() and FX.repair:
        b = ORIG["bitlen"](a)
        FX.repaired += 1
    return b


def fdiv(num, den):
    den = np.asanyarray(den, dtype=np.int64)
    assert (den > 0).all()
    q = num // den
    q = FX.point("look", "division", q)
    bad = FX.check("division bracket", in_range(q * den, num, (q + 1) * den), "division")
    if bad.any() and FX.repair:
        q = num // den
        FX.repaired += 1
    return q


def isqrt(n):
    assert (n >= 0).all() and (n < (1 << 62)).all()
    s = np.sqrt(n.astype(np.float64)).astype(np.int64)
    for _ in range(4):
        s = np.where(s * s > n, s - 1, s)
        s = np.where((s + 1) * (s + 1) <= n, s + 1, s)
    s = FX.point("look", "square root", s)
    bad = FX.check("square root bracket", in_range(s * s, n, (s + 1) * (s + 1)), "square root")
    if bad.any() and FX.repair:
        s = ORIG["isqrt"](n)
        FX.repaired += 1
    return s


def peel_index(x, k):
    i1 = ORIG["peel_index"](x, k)
    return twice("peel selection twice", "peel selection", i1, ORIG["peel_index"](x, k))


def install():
    for f in ("shift_round", "rshift_round", "bitlen", "fdiv", "isqrt", "peel_index"):
        if f not in ORIG:
            ORIG[f] = getattr(X, f)
        setattr(X, f, globals()[f])


class Checked16(X.Exact16):
    """Exact16 with the spare rows on every product and the looks checked; FX holds the faults and the checks."""

    def __init__(self, route="f64"):
        super().__init__(route)
        install()
        self.spares = {}

    def spare(self, name):
        """The two spare rows of a weight matrix, made once from the stored 16-bit weights: int64 [in]."""
        s = self.spares.get(name)
        if s is None:
            w = self.W16[name]                                                # int16 [in, out]
            c1 = np.zeros(w.shape[0], dtype=np.int64)
            c2 = np.zeros(w.shape[0], dtype=np.int64)
            for c in range(0, w.shape[1], 8192):
                blk = np.asarray(w[:, c:c + 8192], dtype=np.int64)
                j = np.arange(c + 1, c + 1 + blk.shape[1], dtype=np.int64)
                c1 += blk.sum(axis=1)
                c2 += (blk * j).sum(axis=1)
            s = self.spares[name] = (c1, c2)
        return s

    def forward(self, ids, pos, cache, kvalid):
        self._layer = 0
        if cache is None:
            self.kstate = {}
        return super().forward(ids, pos, cache, kvalid)

    # ---- the products over the weights ----
    def prepare(self, x, site):
        """As Exact16.prepare (clamped, peel-selected and block-shifted once for every product that reads it), with
        the input's travelling sum made here: per row, the sum of every word a product reads (the 16-bit values, the
        peeled values and their places, the shift)."""
        idx, xp, xb, sh = super().prepare(x, site)
        packed = np.concatenate([xb, xp, idx, sh], axis=1)
        return packed, vector_sum(packed)

    def product(self, prep, name, dtype=np.int64):
        w, g = self.W16[name], self.W16[name + ".g"]
        c1, c2 = self.spare(name)
        packed, made = prep
        packed = read_input(name, packed, made)
        k = X.PEEL16
        n_in = packed.shape[1] - 2 * k - 1
        xb, xp, idx, sh = (packed[:, :n_in], packed[:, n_in:n_in + k], packed[:, n_in + k:n_in + 2 * k],
                           packed[:, n_in + 2 * k:])
        N, nout = xb.shape[0], w.shape[1]
        y = np.empty((N, nout), dtype=dtype)
        S1, S2 = 0, 0
        for c in range(0, nout, 8192):
            wc = FX.point("weight", name, w[:, c:c + 8192])
            T = np.left_shift(X.mm16(xb, wc, self.route, self.mmi), sh)
            for j in range(X.PEEL16):
                T += xp[:, j:j + 1] * wc[idx[:, j]]
            T = FX.point("sum", name, T)
            s1, s2 = two_sums(T, np.arange(c + 1, c + 1 + T.shape[1], dtype=np.int64), 1)
            S1, S2 = S1 + s1, S2 + s2
            blk = X.shift_round(T, g[None, c:c + 8192])
            assert dtype == np.int64 or np.abs(blk).max() < (1 << 31)
            y[:, c:c + 8192] = blk
        bad = rows_check("spare rows", name, S1, S2, spare_product(xb, sh, xp, idx, c1),
                         spare_product(xb, sh, xp, idx, c2))
        if bad.any() and FX.repair:
            E1, E2 = spare_product(xb, sh, xp, idx, c1), spare_product(xb, sh, xp, idx, c2)
            for r in np.nonzero(bad)[0]:
                j = locate(int(S1[r]) - int(E1[r]), int(S2[r]) - int(E2[r]), nout)
                if j is None:
                    continue
                col = np.asarray(w[:, j - 1], dtype=np.int64)
                t = (int(xb[r] @ col) << int(sh[r, 0])) + sum(int(xp[r, p]) * int(col[idx[r, p]])
                                                              for p in range(X.PEEL16))
                gj = int(g[j - 1])
                y[r, j - 1] = (t + (1 << (gj - 1))) >> gj if gj > 0 else t
                FX.repaired += 1
        return y

    # ---- looks made twice ----
    def clamp(self, x, site, layer=None):
        r = super().clamp(x, site, layer)
        c = self.C[site]
        return twice("clamp twice", "clamp", r, np.clip(x, -c, c))

    def exp(self, t):
        return twice("table read twice", "exp table", super().exp(t), super().exp(t))

    def silu(self, x):
        return twice("table read twice", "silu table", super().silu(x), super().silu(x))

    def rope_tables(self, pos):
        c, s = super().rope_tables(pos)
        c2, s2 = super().rope_tables(pos)
        return twice("table read twice", "rotary table", c, c2), twice("table read twice", "rotary table", s, s2)

    def rms(self, x, wname):
        """As Exact.rms, with the shift's bit length through the bracketed bitlen."""
        A, NB = X.A, X.NORM_BITS
        top = np.abs(x).max(-1, keepdims=True)
        sh = np.maximum(0, X.bitlen(top) - NB).astype(np.int64)
        xs = x >> sh
        ss = (xs * xs).sum(-1, keepdims=True)
        ms = X.fdiv(ss, X.HIDDEN)
        assert (sh <= A).all()
        eps = np.array(self.eps, dtype=np.int64)[sh]
        r = X.isqrt(ms + np.maximum(eps, 1))
        y = X.fdiv(x << (A - sh), r)
        assert (np.abs(y) <= X.RMS_Y << A).all()
        return X.rshift_round(y * np.asarray(self.W[wname]), A)

    # ---- the cache and attention ----
    def cache_entry(self, k, v):
        """As Exact16's, plus the two sums of each v half over its 64 values (kept in the cache), and the split put
        back together against v clamped."""
        kb, shk, vh, vl = super().cache_entry(k, v)
        vc = np.clip(v, -self.C["v"], self.C["v"])
        vh = FX.point("look", "v split", vh)
        bad = FX.check("v split put together", (np.left_shift(vh, X.B16 - 1) + vl) == vc, "v split")
        if bad.any() and FX.repair:
            vh = vc >> (X.B16 - 1)
            FX.repaired += 1
        d = np.arange(1, X.HEAD + 1, dtype=np.int64)
        return (kb, shk, vh, vl) + two_sums(vh, d) + two_sums(vl, d)

    def key_sums(self, kb):
        """The two sums of the keys over the cache, kept per layer: the new keys are added as they come."""
        layer = self._layer
        self._layer += 1
        T = kb.shape[2]
        seen, s1, s2 = self.kstate.get(layer, (0, 0, 0))
        n1, n2 = two_sums(kb[:, :, seen:T], np.arange(seen + 1, T + 1, dtype=np.int64)[None, None, :, None], 2)
        s1, s2 = s1 + n1, s2 + n2
        self.kstate[layer] = (T, s1, s2)
        return s1, s2

    def attention(self, q, kb, shk, vh, vl, vs1h, vs2h, vs1l, vs2l, kvalid):
        """As Exact16.attention, with the scores and the two context products checked by their spare rows, the
        softmax maximum and the held p made twice."""
        A, B16, LIM16, mm16 = X.A, X.B16, X.LIM16, X.mm16
        B, _, L, _ = q.shape
        T, G = kb.shape[2], X.HEADS // X.KV
        ks1, ks2 = self.key_sums(kb)
        qm = self.clamp(q, "q")
        qc = read_input("scores q", qm, vector_sum(qm))
        qb, shq, n1 = X.block16(qc)
        qb = qb.reshape(B, X.KV, G * L, X.HEAD)
        S = FX.point("sum", "scores q.k", mm16(qb, kb.swapaxes(-1, -2), self.route, self.mmi))
        t = np.arange(1, T + 1, dtype=np.int64)
        s1, s2 = two_sums(S, t)
        bad = rows_check("spare rows", "scores q.k", s1, s2, spare_dot(qb, ks1[:, :, None, :]),
                         spare_dot(qb, ks2[:, :, None, :]))
        if bad.any() and FX.repair:
            for b_, h, r in zip(*np.nonzero(bad)):
                e1 = int(S[b_, h, r].sum()) - int((qb[b_, h, r] * ks1[b_, h]).sum())
                e2 = int((S[b_, h, r] * t).sum()) - int((qb[b_, h, r] * ks2[b_, h]).sum())
                j = locate(e1, e2, T)
                if j is not None:
                    S[b_, h, r, j - 1] = int(qb[b_, h, r] @ kb[b_, h, j - 1].astype(np.int64))
                    FX.repaired += 1
        S = S.reshape(B, X.KV, G, L, T)
        s = np.left_shift(S, shq.reshape(B, X.KV, G, L, 1) + shk[:, :, None].swapaxes(-1, -2))
        key = kvalid[:, None, None]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        m = twice("softmax maximum twice", "softmax maximum", m, np.where(key, s, -(1 << 62)).max(-1, keepdims=True))
        t_ = np.maximum(m - s, 0) >> (A + 3)
        e = np.where(key, self.exp(t_), 0)
        p = X.shift_round(X.fdiv(e << A, e.sum(-1, keepdims=True)), 1)       # at 2^-15
        self.p_held += int((p > LIM16).sum())
        pm = twice("held p twice", "held p", np.minimum(p, LIM16), np.minimum(p, LIM16)).reshape(B, X.KV, G * L, T)
        pb = read_input("context p", pm, vector_sum(pm))
        self.extra += n1
        d = np.arange(1, X.HEAD + 1, dtype=np.int64)
        halves = []
        for name, vv, vs1, vs2 in (("context p.vh", vh, vs1h, vs2h), ("context p.vl", vl, vs1l, vs2l)):
            Cc = FX.point("sum", name, mm16(pb, vv, self.route, self.mmi))
            s1, s2 = two_sums(Cc, d)
            bad = rows_check("spare rows", name, s1, s2, spare_dot(pb, vs1[:, :, None, :]),
                             spare_dot(pb, vs2[:, :, None, :]))
            if bad.any() and FX.repair:
                for b_, h, r in zip(*np.nonzero(bad)):
                    e1 = int(Cc[b_, h, r].sum()) - int((pb[b_, h, r] * vs1[b_, h]).sum())
                    e2 = int((Cc[b_, h, r] * d).sum()) - int((pb[b_, h, r] * vs2[b_, h]).sum())
                    j = locate(e1, e2, X.HEAD)
                    if j is not None:
                        Cc[b_, h, r, j - 1] = int(pb[b_, h, r] @ vv[b_, h, :, j - 1].astype(np.int64))
                        FX.repaired += 1
            halves.append(Cc)
        c = np.left_shift(halves[0], B16 - 1) + halves[1]
        ctx = X.shift_round(c, B16 - 1)
        return ctx.reshape(B, X.KV, G, L, X.HEAD).reshape(B, X.HEADS, L, X.HEAD)


# ---- the runs ------------------------------------------------------------------------------------------------------
def short_run(m, ids, gen):
    """One prompt at batch 1: the prefill, then gen - 1 greedy steps with the cache. Returns the hash of every logit
    and the tokens."""
    h = hashlib.sha256()
    L = len(ids)
    x = np.array(ids, dtype=np.int64)[None]
    pos = np.arange(L)[None]
    kvalid = np.tril(np.ones((L, L), dtype=bool))[None]
    lg, cache = m.forward(x, pos, None, kvalid)
    h.update(np.ascontiguousarray(lg).tobytes())
    toks = [int(np.argmax(lg[0, -1]))]
    for t in range(gen - 1):
        T = L + t + 1
        lg, cache = m.forward(np.array([[toks[-1]]]), np.array([[L + t]]), cache, np.ones((1, 1, T), dtype=bool))
        h.update(np.ascontiguousarray(lg).tobytes())
        toks.append(int(np.argmax(lg[0, -1])))
    return h.hexdigest(), toks


def campaign(route, n, seed, gen=4):
    """n single faults of each kind at places drawn uniformly over the run's fault points; each run once as it is
    (the checks record, the fault goes on) and once with the repairs."""
    global FX
    m = Checked16(route)
    ids = X.tokenizer().encode(X.prompts()[0])
    FX = Faults(survey=True)
    t0 = time.time()
    h0, toks0 = short_run(m, ids, gen)
    clean = time.time() - t0
    assert not FX.fired, FX.fired
    seen, widths = dict(FX.seen), dict(FX.top)
    print("campaign: route %s, prompt 0 (%d tokens) and %d tokens, clean run %.2f s, no check fired" % (
        route, len(ids), gen, clean))
    print("fault points over the run: %s" % ", ".join("%s %d" % kv for kv in seen.items()))
    rng = np.random.default_rng(seed)
    rows = []
    for kind in KINDS:
        for _ in range(n):
            arm = (kind, int(rng.integers(seen[kind])), float(rng.random()))
            res = {"kind": kind}
            for repair in (False, True):
                FX = Faults(arm, widths, repair)
                try:
                    h, toks = short_run(m, ids, gen)
                    stopped = None
                except (AssertionError, IndexError, ValueError, OverflowError) as why:
                    h, toks, stopped = None, None, type(why).__name__
                if not repair:
                    res.update(hit=FX.hit, stopped=stopped, fired=sorted({f[0] for f in FX.fired}),
                               logit=h != h0, token=toks != toks0)
                else:
                    res.update(repaired=FX.repaired, unchanged=h == h0)
            rows.append(res)
    return seen, widths, rows


def table(rows):
    print("| fault | injected | changed a logit | changed a token | caught | caught by | repaired, hash unchanged |")
    print("| --- | ---: | ---: | ---: | ---: | --- | ---: |")
    for kind in KINDS:
        rs = [r for r in rows if r["kind"] == kind]
        caught = [r for r in rs if r["fired"] or r["stopped"]]
        where = collections.Counter()
        for r in caught:
            where.update(r["fired"] or ["an assertion (%s)" % r["stopped"]])
        print("| %s | %d | %d | %d | %d | %s | %d |" % (
            KIND_TEXT[kind], len(rs), sum(r["logit"] for r in rs), sum(r["token"] for r in rs), len(caught),
            "; ".join("%s %d" % kv for kv in sorted(where.items())) or "-", sum(r["unchanged"] for r in caught)))
    esc = [r for r in rows if not (r["fired"] or r["stopped"]) and r["logit"]]
    print("not caught and changed a logit: %d" % len(esc))
    for r in esc[:20]:
        print("  %s %s" % (r["kind"], r["hit"]))


def main(argv):
    global FX
    arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    route = arg("--route", "f64")
    if len(argv) > 1 and argv[1] == "hash":
        t0 = time.time()
        if "--plain" in argv:
            m = X.Exact16(route)
        else:
            m = Checked16(route)
            FX = Faults()
        hl, hc, _, _ = X.prompt_run(m, 8)
        ok = (hl, hc) == X.expected(16)
        print("%s route %s: logits %s continuations %s %s, %.0f s" % (
            "plain  " if "--plain" in argv else "checked", route, hl, hc, "MATCH" if ok else "DIFFERENT",
            time.time() - t0))
        if "--plain" not in argv:
            print("checks made: %s; fired: %d %s" % (", ".join("%s %d" % kv for kv in sorted(FX.checks.items())),
                                                      len(FX.fired), FX.fired[:5]))
            ok = ok and not FX.fired
        return 0 if ok else 1
    if len(argv) > 1 and argv[1] == "campaign":
        n, seed = int(arg("--n", "100")), int(arg("--seed", "1"))
        t0 = time.time()
        seen, widths, rows = campaign(route, n, seed)
        table(rows)
        print("campaign time %.0f s" % (time.time() - t0))
        if arg("--save", None):
            json.dump({"seen": seen, "widths": {"%s %s" % k: v for k, v in widths.items()}, "rows": rows},
                      open(arg("--save", None), "w"), indent=0, default=str)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
