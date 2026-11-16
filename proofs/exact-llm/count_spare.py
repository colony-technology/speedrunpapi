"""Census of every NumPy operation in the forward pass of exact_llm.Exact16 and spare_row.Checked16 (route f64), per
token: count_ops.py's method, with the frames of spare_row.py counted under their own names (prefixed "S.").

usage: python -I count_spare.py FOLDER OUT.json

The wrappers that spare_row installs over exact_llm's looks (shift_round, rshift_round, bitlen, peel_index) and the
helper twice() are passed over when they are not the innermost frame, so the look they wrap is counted where
Exact16 counts it; the bracket or the second evaluation is counted in the wrapper. Windows as count_ops.py: last
(context 64), prefill (64 tokens), last32. The weights are zero arrays of the pinned shapes, the spare rows made
from them before counting.
"""
import collections
import json
import linecache
import math
import os
import sys

import numpy as np

sys.path.insert(0, sys.argv[1])
import exact_llm as X  # noqa: E402
import spare_row as S  # noqa: E402

SRCS = {os.path.abspath(X.__file__): "", os.path.abspath(S.__file__): "S."}
PASS = {"_round", "shift_round", "rshift_round", "bitlen", "peel_index", "twice", "clamp", "exp", "silu",
        "rope_tables"}
TALLY = collections.Counter()
ON = [False]


def caller():
    """(function, line, parent, parent's line, grandparent) of the innermost exact_llm or spare_row frames. Above an
    exact_llm look, spare_row's wrapper of it is passed over, so the look keeps the parent Exact16 gives it."""
    f, chain, inner_exact = sys._getframe(2), [], None
    while f is not None and len(chain) < 3:
        path = os.path.abspath(f.f_code.co_filename)
        name = f.f_code.co_name
        if path in SRCS and name != "<genexpr>":
            pre = SRCS[path]
            if inner_exact is None:
                inner_exact = not pre
            if not (pre and chain and inner_exact and name in PASS):
                chain.append((pre + name, linecache.getline(path, f.f_lineno).strip()))
        f = f.f_back
    chain += [("", "")] * (3 - len(chain))
    if not chain[0][0]:
        return ("harness", "", "", "", "")
    return (chain[0][0], chain[0][1], chain[1][0], chain[1][1], chain[2][0])


class Count(np.ndarray):
    def __array_ufunc__(self, ufunc, method, *inputs, **kw):
        raw = [i.view(np.ndarray) if isinstance(i, Count) else i for i in inputs]
        out = kw.get("out")
        if out:
            kw["out"] = tuple(o.view(np.ndarray) if isinstance(o, Count) else o for o in out)
        res = getattr(ufunc, method)(*raw, **kw)
        if ON[0]:
            ON[0] = False
            shapes = [tuple(getattr(i, "shape", ())) for i in raw]
            if ufunc is np.matmul:
                n = math.prod(res.shape) * shapes[0][-1]
            elif method == "reduce":
                n = math.prod(shapes[0])
            else:
                n = math.prod(np.broadcast_shapes(*shapes))
            try:
                TALLY[caller() + (ufunc.__name__ + ("" if method == "__call__" else "." + method),)] += n
            finally:
                ON[0] = True
        if out:
            return out[0] if len(out) == 1 else out
        return wrap(res)

    def __array_function__(self, func, types, args, kwargs):
        if ON[0]:
            ON[0] = False
            try:
                name = func.__name__
                shape = lambda a: tuple(getattr(a, "shape", ()))
                if name in ("where",):
                    n = math.prod(np.broadcast_shapes(*[shape(a) for a in args[:3]]))
                elif name in ("take_along_axis", "put_along_axis"):
                    n = math.prod(shape(args[1]))
                else:
                    n = math.prod(shape(args[0]))
                TALLY[caller() + (name,)] += n
                res = super().__array_function__(func, types, args, kwargs)
            finally:
                ON[0] = True
            return wrap(res)
        return wrap(super().__array_function__(func, types, args, kwargs))

    def __getitem__(self, idx):
        res = super().__getitem__(idx)
        parts = idx if isinstance(idx, tuple) else (idx,)
        if ON[0] and any(isinstance(p, np.ndarray) and p.dtype != bool for p in parts):
            ON[0] = False
            try:
                TALLY[caller() + ("gather",)] += math.prod(getattr(res, "shape", ()))
            finally:
                ON[0] = True
        return res


def wrap(r):
    if isinstance(r, tuple):
        return tuple(wrap(x) for x in r)
    if isinstance(r, np.ndarray) and not isinstance(r, Count):
        return r.view(Count)
    return r


class NP:
    """numpy for exact_llm's and spare_row's own calls: asarray keeps the subclass, array returns a Count view."""
    def __getattr__(self, k):
        return getattr(np, k)

    @staticmethod
    def asarray(a, dtype=None, order=None):
        return np.asanyarray(a, dtype=dtype, order=order)

    @staticmethod
    def array(*a, **k):
        r = np.array(*a, **k)
        return r.view(Count) if isinstance(r, np.ndarray) else r

    @staticmethod
    def empty(*a, **k):
        return np.empty(*a, **k).view(Count)


X.np = NP()
S.np = NP()


def zeros_like_file(path):
    m = np.load(path, mmap_mode="r")
    return np.broadcast_to(np.zeros((), dtype=m.dtype), m.shape)


def zero_weights(d, keep_1d=True):
    W = {}
    for f in os.listdir(d):
        if f.endswith(".npy"):
            p = os.path.join(d, f)
            m = np.load(p, mmap_mode="r")
            if f.endswith(".g.npy") or (keep_1d and m.ndim == 1):
                W[f[:-4]] = np.asarray(m)
            else:
                W[f[:-4]] = zeros_like_file(p)
    return W


def model(kind):
    """Exact16 or Checked16 on zero weights, set up without reading model.safetensors."""
    W32 = zero_weights(os.path.join(X.MCACHE, "int32-wb%d" % X.WB))
    W16 = zero_weights(os.path.join(X.MCACHE, "int16-rows"))
    st = X.weight_stats16()
    m = object.__new__(S.Checked16 if kind == "checked16" else X.Exact16)
    X.Exact.__init__(m, W=W32, clamps=X.clamps16(st))
    m.W16, m.stats16, m.route, m.mmi, m.extra, m.p_held = W16, st, "f64", None, 0, 0
    if kind == "checked16":
        S.install()
        S.FX = S.Faults()
        m.spares, m.kstate, m._layer = {}, {}, 0
        for name in W16:
            if not name.endswith(".g") and W16[name].ndim == 2:
                m.spare(name)
    m.E = W32["model.embed_tokens.weight"].view(Count)
    for t in ("Et", "St", "cos", "sin"):
        setattr(m, t, getattr(m, t).view(Count))
    return m


def window(m, L, cached):
    """Count one forward: the last token of L with a cache of L - 1 (cached) or the whole prefill of L."""
    ids = np.zeros((1, L), dtype=np.int64)
    pos = np.arange(L)[None]
    i = np.arange(L)
    kvalid = (i[None, None, :] <= i[None, :, None])
    TALLY.clear()
    if cached:
        _, cache = m.forward(ids[:, :L - 1], pos[:, :L - 1], None, kvalid[:, :L - 1, :L - 1])
        ON[0] = True
        logits, _ = m.forward(ids[:, L - 1:], pos[:, L - 1:], cache, kvalid[:, L - 1:, :])
    else:
        ON[0] = True
        logits, _ = m.forward(ids, pos, None, kvalid)
    np.argmax(np.asarray(logits).view(Count)[0, -1])
    ON[0] = False
    return dict(TALLY)


out = {}
for kind in ("exact16", "checked16"):            # Exact16 first: Checked16 installs its wrappers over exact_llm
    m = model(kind)
    for name, L, cached in (("last", 64, True), ("prefill", 64, False), ("last32", 32, True)):
        t = window(m, L, cached)
        out["%s %s" % (kind, name)] = [list(k) + [v] for k, v in sorted(t.items())]
        print(kind, name, "operations recorded:", len(t), "elements:", sum(t.values()))
    if kind == "checked16":
        print("checks made in the last window:", dict(S.FX.checks), "fired:", len(S.FX.fired))
    del m
json.dump(out, open(sys.argv[2], "w"), indent=0)
