"""Census of every NumPy operation in the forward pass of exact_llm.Exact and exact_llm.Exact16 (route f64), per token.

usage: python -I count_ops.py FOLDER OUT.json

Three windows, as exact_llm runs them:
  last: the decode step that makes position 64 (context length 64): a prefill of 63 tokens, then one forward of one
        token with the key-value cache, then the greedy argmax over the vocabulary;
  prefill: one forward of 64 tokens and the argmax at its last position; totals / 64;
  last32: as last, at context length 32 (with last, the cost per key read).
Every array the model makes is a Count array (an ndarray subclass). Its __array_ufunc__, __array_function__ and
__getitem__ (index arrays) record the operation, its element count (multiply-adds for matmul: output size x inner
width; the input size for a reduction), and the exact_llm source line and function that called it. exact_llm's
np.asarray is given as np.asanyarray and np.array returns a Count view, so the arrays stay Count arrays; nothing
else in exact_llm changes. Inside a NumPy function (np.where, np.clip, argmax, ...) only the function is recorded.
The weights are zero arrays of the pinned shapes (zero strides): no operation count depends on a value (every
branch is np.where over whole arrays, the loops have fixed lengths), so the census is that of the real weights.
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

SRC = os.path.abspath(X.__file__)
TALLY = collections.Counter()
ON = [False]


def caller():
    """(function, line, parent function, parent's line, grandparent function) of the innermost exact_llm frames
    (a generator expression counts as its function), or the harness."""
    f, chain = sys._getframe(2), []
    while f is not None and len(chain) < 3:
        if os.path.abspath(f.f_code.co_filename) == SRC and f.f_code.co_name != "<genexpr>":
            chain.append((f.f_code.co_name, linecache.getline(SRC, f.f_lineno).strip()))
        f = f.f_back
    chain += [("", "")] * (3 - len(chain))
    if not chain[0][0]:
        return ("harness", "", "", "", "")
    return (chain[0][0], chain[0][1], chain[1][0], chain[1][1], chain[2][0])


def record(op, n):
    if ON[0] and n:
        TALLY[caller() + (op,)] += int(n)


class Count(np.ndarray):
    def __array_ufunc__(self, ufunc, method, *inputs, **kw):
        raw = [i.view(np.ndarray) if isinstance(i, Count) else i for i in inputs]
        out = kw.get("out")
        if out:
            kw["out"] = tuple(o.view(np.ndarray) if isinstance(o, Count) else o for o in out)   # same memory
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
        if out:                                       # in place (T += ...): hand back the caller's own arrays
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
    """numpy for exact_llm's own calls: asarray keeps the subclass, array returns a Count view."""
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
    def empty(*a, **k):                               # outputs filled block by block (product, logits)
        return np.empty(*a, **k).view(Count)


X.np = NP()


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
                W[f[:-4]] = np.asarray(m)                    # row scales and norm weights: small, real
            else:
                W[f[:-4]] = zeros_like_file(p)
    return W


def model(kind):
    W32 = zero_weights(os.path.join(X.CACHE, "int32-wb%d" % X.WB))
    if kind == "exact":
        m = X.Exact(W=W32)
    else:
        m = X.Exact16("f64")
        m.W, m.W16 = W32, zero_weights(os.path.join(X.CACHE, "int16-rows"))
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
    np.argmax(np.asarray(logits).view(Count)[0, -1])          # run_prompts: the greedy token
    ON[0] = False
    return dict(TALLY)


out = {}
for kind in ("exact", "exact16"):
    m = model(kind)
    for name, L, cached in (("last", 64, True), ("prefill", 64, False), ("last32", 32, True)):
        t = window(m, L, cached)
        out["%s %s" % (kind, name)] = [list(k) + [v] for k, v in sorted(t.items())]
        print(kind, name, "operations recorded:", len(t), "elements:", sum(t.values()))
    del m
json.dump(out, open(sys.argv[2], "w"), indent=0)
