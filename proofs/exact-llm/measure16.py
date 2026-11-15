# usage: python -I measure16.py FOLDER RUNS_DIR NAME [--ib B] [--wb B] [--ab B] [--peel K]
#
# One row of the exact-16 table: the integer model with its product operands narrowed, against the saved float32 runs
# (RUNS_DIR/float32.*: prompt logits, 48-token continuations, text nll and top-1).
#   --ib B   every product input (linear inputs, logits input) block-scaled per token vector to B-bit signed integers:
#            sh = max(0, bitlen(max |x|) - (B - 1)), x_B = round(x / 2^sh), one more shift if rounding reaches 2^(B-1)
#   --wb B   every weight matrix (and the tied output embedding) scaled per output row to B-bit signed integers from
#            the published bfloat16 values: g = largest exponent with max |w| 2^g <= 2^(B-1) - 1, w_B = round(w 2^g)
#   --ab B   attention: q and k block-scaled per head vector, v per head over all keys, p held at 2^-(B-1)
#   --peel K the K largest |x| of each product input vector kept as exact wide terms (int64 against the 2^-16 weights)
# Prints the row: prompts top-1, largest and mean |logit difference|, continuations equal, text top-1, perplexity,
# and how many vectors needed the extra shift.
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, sys.argv[1])
import exact_llm as X  # noqa: E402

runs, name = sys.argv[2], sys.argv[3]
arg = lambda k: int(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else 0
IB, WBQ, AB, PEEL = arg("--ib"), arg("--wb"), arg("--ab"), arg("--peel")
QUICK = "--quick" in sys.argv


def bitlen(a):
    return np.frexp(a.astype(np.float64))[1].astype(np.int64)


def shift_round(v, k):
    """v * 2^-k rounded (half up) for k > 0, v * 2^-k exactly for k <= 0; k broadcasts."""
    k = np.broadcast_to(k, v.shape)
    kp = np.maximum(k, 0)
    r = (v + np.where(kp > 0, np.left_shift(1, np.maximum(kp - 1, 0)), 0)) >> kp
    return np.where(k > 0, r, np.left_shift(v, np.maximum(-k, 0)))


class Q(X.Exact):
    def __init__(self):
        super().__init__(keep_f64=False)
        self.extra, self.peeled, self.pclip, self.sites, self.gm = 0, 0, 0, {}, {}
        self.qw = {}
        if WBQ:
            lim = (1 << (WBQ - 1)) - 1
            for nm, a in X.iter_safetensors(X.model_file("model.safetensors")):
                if a.ndim != 2:
                    continue
                top = np.abs(a).max(1).astype(np.float64)            # a: float32 [out, in] (the embedding [V, 576])
                e = np.frexp(top)[1]
                g = (WBQ - 1) - e
                g = np.where(top * np.exp2(g) > lim, g - 1, g)
                wq = np.rint(a * np.exp2(g).astype(np.float32)[:, None])   # power-of-two scaling: exact in float32
                assert np.abs(wq).max() <= lim
                self.qw[nm] = (np.ascontiguousarray(wq.T).astype(np.int16 if WBQ <= 16 else np.int32), g.astype(np.int64))
                kind = ".".join(nm.split(".")[-3:-1]) if ".layers." in nm else nm.split(".")[-2]
                lo, hi = self.gm.get(kind, (99, -99))
                self.gm[kind] = (min(lo, int(g.min())), max(hi, int(g.max())))
                del wq

    def block(self, x, bits, axes=-1, site=None):
        lim = (1 << (bits - 1)) - 1
        top = np.abs(x).max(axis=axes, keepdims=True)
        sh = np.maximum(0, bitlen(top) - (bits - 1))
        xb = shift_round(x, sh)
        over = (np.abs(xb) > lim).any(axis=axes, keepdims=True)
        if over.any():
            self.extra += int(over.sum())
            sh = sh + over
            xb = shift_round(x, sh)
        assert (np.abs(xb) <= lim).all()
        st = self.sites.setdefault(site or self._site, [99, -1, 0, 0])   # shift min, max, vectors, extra shifts
        st[0], st[1] = min(st[0], int(sh.min())), max(st[1], int(sh.max()))
        st[2], st[3] = st[2] + int(sh.size), st[3] + int(over.sum())
        return xb, sh

    def product(self, x, name, wint):
        """x int64 [N, in] at 2^-16 against the matrix `name`; result at 2^-16.
        y = round((2^sh S + sum of peeled x w) 2^-g): the peeled values (exact, wide) against the same weights as
        the product, one rounding per output."""
        if PEEL:
            idx = np.argpartition(-np.abs(x), PEEL - 1, axis=-1)[:, :PEEL]
            xp = np.take_along_axis(x, idx, -1)
            x = x.copy()
            np.put_along_axis(x, idx, 0, -1)
            self.peeled += int(xp.size)
        if IB:
            xb, sh = self.block(x, IB)
        else:
            xb, sh = x, np.zeros((x.shape[0], 1), np.int64)
        xf = xb.astype(np.float64)
        wsrc = self.qw[name][0] if WBQ else wint
        nin, nout = wsrc.shape
        y = np.empty((x.shape[0], nout), dtype=np.int64)
        for c in range(0, nout, 8192):                               # output columns in blocks: little memory
            cs = slice(c, c + 8192)
            w = np.asarray(wsrc[:, cs], dtype=np.float64)
            if WBQ:
                n = nin if IB else 256                               # inputs as now: chunk to stay below 2^53
            else:
                n = nin if IB else X.SPLIT.get(self._site, nin)
            S = sum((xf[:, s:s + n] @ w[s:s + n]).astype(np.int64) for s in range(0, nin, n))
            g = self.qw[name][1][None, cs] if WBQ else X.A
            if PEEL:
                wcols = np.asarray(wsrc[:, cs], dtype=np.int64)
                T = np.left_shift(S, sh) + sum(xp[:, j:j + 1] * wcols[idx[:, j]] for j in range(PEEL))
                yc = shift_round(T, np.broadcast_to(g, T.shape))
            else:
                yc = shift_round(S, g - sh)
            y[:, cs] = yc
        return y

    def linear(self, x, name, site):
        self._site = site
        return self.product(self.clamp(x, site), name, self.W[name])

    def logits(self, h):
        hc = self.clamp(h, "logits input")
        out = np.empty((h.shape[0], X.VOCAB), dtype=np.int32)
        if WBQ or IB or PEEL:
            if WBQ:
                self.qw["lm_head"] = self.qw["model.embed_tokens.weight"]
            if not WBQ and "lm_head" not in self.W:              # the 2^-16 embedding, only where it is used
                self.W["lm_head"] = np.ascontiguousarray(np.asarray(self.E, dtype=np.int32).T)   # [576, V]
            Et = self.W.get("lm_head", self.qw.get("lm_head", (None,))[0])
            self._site = "logits input"
            y = self.product(hc, "lm_head", Et)
            assert np.abs(y).max() < (1 << 31)
            out[:] = y
            return out
        return super().logits(h)

    def attention(self, q, k, v, kvalid):
        if not AB:
            return super().attention(q, k, v, kvalid)
        B, _, L, _ = q.shape
        q, k, v = self.clamp(q, "q"), self.clamp(k, "k"), self.clamp(v, "v")
        qb, shq = self.block(q, AB, site="q")                                # per head vector
        kb, shk = self.block(k, AB, site="k")
        qb = qb.reshape(B, X.KV, X.HEADS // X.KV, L, X.HEAD)
        shq = shq.reshape(B, X.KV, X.HEADS // X.KV, L, 1)
        S = (qb.astype(np.float64) @ kb.astype(np.float64)[:, :, None].swapaxes(-1, -2)).astype(np.int64)
        s = np.left_shift(S, shq + shk[:, :, None].swapaxes(-1, -2))   # at 2^-32
        key = kvalid[:, None, None]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - s, 0) >> (X.A + 3)
        e = np.where(key, self.exp(t), 0)
        p = X.fdiv(e << X.A, e.sum(-1, keepdims=True))               # at 2^-16
        pr = shift_round(p, X.A - (AB - 1))
        self.pclip += int((pr > (1 << (AB - 1)) - 1).sum())
        pb = np.minimum(pr, (1 << (AB - 1)) - 1)                      # at 2^-(AB-1)
        vb, shv = self.block(v, AB, axes=(-2, -1), site="v")                  # per (row, kv head) over keys and dims
        ctx = (pb.astype(np.float64) @ vb.astype(np.float64)[:, :, None]).astype(np.int64)
        ctx = shift_round(ctx, (AB - 1) - shv[:, :, None])           # 2^-(AB-1) x 2^(shv-16) -> 2^-16
        return ctx.reshape(B, X.HEADS, L, X.HEAD)


t0 = time.time()
m = Q()
tok = X.tokenizer()
kept = []
if QUICK:
    X.run_prompts(m, tok, X.prompts()[:4], 4, None, gen=3)
    X.text_windows.__defaults__ = (1, 64)
    X.text_run(m)
    print("%s quick: ran (%.0f s)" % (name, time.time() - t0))
    sys.exit(0)
cont = X.run_prompts(m, tok, X.prompts(), 8, lambda r, lg: kept.append(np.array(lg)))
f_all = np.load(runs + "/float32.logits.npy", mmap_mode="r")
fc = np.load(runs + "/float32.cont.npy")
top1, dmax, dsum, npos, at = 0, 0.0, 0.0, 0, 0
for lg in kept:                                                      # prompt by prompt: little memory
    e = lg.astype(np.float64) / 2.0 ** 16
    f = np.asarray(f_all[at:at + lg.shape[0]], dtype=np.float64)
    at += lg.shape[0]
    d = np.abs(e - f)
    top1 += int((e.argmax(-1) == f.argmax(-1)).sum())
    dmax, dsum, npos = max(dmax, float(d.max())), dsum + float(d.sum()), npos + d.size
del kept
nll, top = X.text_run(m)
fn, ft = np.load(runs + "/float32.nll.npy"), np.load(runs + "/float32.top.npy")
print("%-22s prompts top-1 %d/%d | logit diff max %.4f mean %.5f | continuations %d/64 | text top-1 %d/%d | "
      "perplexity %.4f (float32 %.4f) | extra shifts %d | clamped %d | %.0f s" % (
          name, top1, at, dmax, dsum / npos,
          int(sum((np.array(a) == b).all() for a, b in zip(cont, fc))), int((top == ft).sum()), ft.size,
          math.exp(nll.mean()), math.exp(fn.mean()), m.extra, sum(m.clamped.values()), time.time() - t0))
# per site: peak |x| (units of 2^-16), present clamp, block shift min/max (f = 16 - shift), vectors, extra shifts
sites = {s: {"peak": int(m.peak.get(s, 0)), "clamp": int(m.C.get(s, 0)), "shift": [v[0], v[1]],
             "f": [16 - v[1], 16 - v[0]], "vectors": v[2], "extra": v[3], "clamped": int(m.clamped.get(s, 0))}
         for s, v in m.sites.items()}
json.dump({"row": name, "flags": sys.argv[4:], "sites": sites, "g_m": m.gm, "peeled": m.peeled,
           "p_held_at_max": m.pclip, "clamped": {k: int(v) for k, v in m.clamped.items()}},
          open(os.path.join(os.path.dirname(runs), "record", "e16-sites-%s.json" % name), "w"), indent=1)
