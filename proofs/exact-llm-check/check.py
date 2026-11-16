"""Checks a claimed exact run of SmolLM2-135M from its trace, without the matrix products.

    python3 -I check.py --exact DIR/proofs/exact-llm --cache CACHE --wdir WEIGHTS_DIR --trace TRACE_DIR
                        [--logits freivalds|direct] [--faults N --seed S]

Written from the README of proofs/exact-llm (its method table); shares no code with exact_llm.py.  Reads the pinned
files itself (pins.json digests): model.safetensors, tokenizer.json, the prompts, the four tables.

For every forward call of the batch, in order, the checker recomputes every element-wise step (embedding, clamps,
RMS norm with its integer square root, rotary step, softmax with the exp table, SiLU table, rounding shifts) and
takes each matrix product's integer sum from the trace as a hint, checked by Freivalds' identity:
    S r == x (W r)   over GF(p), for p in (2^31 - 1, 2^31 - 19), two random r for each prime,
r drawn from os.urandom after the trace exists, W r computed once per matrix.  Every hint is first required to
satisfy |S| <= 2^53 (bounds.json: every true sum does).  A wrong hint then differs from the true sum by a vector D
with 0 < |D_i| < 2^54 < p1 p2 for some i, so D is non-zero modulo p1 or modulo p2; for that prime each random r
misses D with probability at most 1/p, so a wrong hint is accepted with probability at most 2^-61.99 per product.
Attention: scores by s r == q (K^T r) with K^T r kept up to date as keys arrive; contexts by ctx r == p (V r).
Logits: by Freivalds on the hinted sums, or (--logits direct) computed here, h E^T in float64 (exact: bound 2^53).
Greedy tokens are taken from the checked logits and must equal the claimed continuation.
--faults N: at each product the hint is also tried with one integer changed by one at a few places, N in all over
the batch; each must fail the check.  The state before a product does not depend on its own hint, so this is the
verdict the checker reaches on a trace with that one change.
"""
import argparse
import gzip
import hashlib
import json
import os
import struct
import sys
import time
import unicodedata
from fractions import Fraction
from pathlib import Path

import numpy as np

LAYERS, HIDDEN, HEADS, KV, HEAD, FF, VOCAB = 30, 576, 9, 3, 64, 1536, 49152
PRIMES = (2 ** 31 - 1, 2 ** 31 - 19)
BOUND = 2 ** 53
CLAMP = {"residual": 16, "attention input": 12, "q": 7, "k": 7, "v": 12, "o input": 12, "mlp input": 11, "gate": 12,
         "up": 12, "down input": 13, "logits input": 14}                    # log2 of the real clamp, README table


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ---- integer primitives, README "Method" ------------------------------------------------------------------------
def rnd(v, k):
    """round(v / 2^k) = (v + 2^(k-1)) >> k."""
    return (v + (1 << (k - 1))) >> k if k else v


def floordiv(n, d):
    q = n // d
    assert ((q * d <= n) & (n < (q + 1) * d)).all()
    return q


def int_sqrt(n):
    assert (n >= 0).all() and (n < (1 << 62)).all()
    s = np.sqrt(n.astype(np.float64)).astype(np.int64)
    for _ in range(4):
        s = np.where(s * s > n, s - 1, s)
        s = np.where((s + 1) * (s + 1) <= n, s + 1, s)
    assert ((s * s <= n) & ((s + 1) * (s + 1) > n)).all()
    return s


def clamp(x, site):
    c = 1 << (CLAMP[site] + 16)
    return np.clip(x, -c, c)


# ---- weights from model.safetensors ------------------------------------------------------------------------------
def weights(model_path, wdir):
    wdir.mkdir(parents=True, exist_ok=True)
    if not (wdir / "DONE").exists():
        with open(model_path, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            head = json.loads(f.read(n))
            base = 8 + n
            for name, m in head.items():
                if name == "__metadata__":
                    continue
                assert m["dtype"] == "BF16"
                f.seek(base + m["data_offsets"][0])
                raw = np.frombuffer(f.read(m["data_offsets"][1] - m["data_offsets"][0]), dtype="<u2").reshape(m["shape"])
                if raw.ndim == 2:
                    out = np.empty(raw.shape, dtype=np.int32)
                    for s in range(0, raw.shape[0], 4096):
                        v = (raw[s:s + 4096].astype(np.uint32) << 16).view(np.float32).astype(np.float64) * 65536.0
                        out[s:s + 4096] = np.rint(v).astype(np.int32)        # ties to even
                    if name != "model.embed_tokens.weight":
                        out = np.ascontiguousarray(out.T)                    # [in, out]
                else:
                    out = np.rint((raw.astype(np.uint32) << 16).view(np.float32).astype(np.float64) * 65536.0).astype(np.int64)
                np.save(wdir / (name + ".npy"), out)
        (wdir / "DONE").write_text("from model.safetensors %s\n" % sha(model_path))
    return {p.name[:-4]: np.load(p, mmap_mode="r") for p in wdir.glob("*.npy")}


# ---- tokenizer from tokenizer.json -------------------------------------------------------------------------------
class BPE:
    def __init__(self, path):
        t = json.load(open(path, encoding="utf-8"))
        self.vocab = t["model"]["vocab"]
        self.rank = {tuple(m.split(" ")) if isinstance(m, str) else tuple(m): i for i, m in enumerate(t["model"]["merges"])}
        bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + list(range(ord("\xae"), ord("\xff") + 1))
        cs, k = list(bs), 0
        for b in range(256):
            if b not in bs:
                bs.append(b)
                cs.append(256 + k)
                k += 1
        self.byte = {b: chr(c) for b, c in zip(bs, cs)}

    @staticmethod
    def letter(c):
        return unicodedata.category(c).startswith("L")

    @staticmethod
    def number(c):
        return unicodedata.category(c).startswith("N")

    def pieces(self, s):
        """Digits split singly, then the GPT-2 pattern on each piece."""
        parts, cur = [], ""
        for c in s:
            if c.isdigit() and self.number(c) and unicodedata.category(c) == "Nd":
                if cur:
                    parts.append(cur)
                parts.append(c)
                cur = ""
            else:
                cur += c
        if cur:
            parts.append(cur)
        out = []
        for p in parts:
            out += self.gpt2(p)
        return out

    def gpt2(self, s):
        out, i, n = [], 0, len(s)
        other = lambda c: not c.isspace() and not self.letter(c) and not self.number(c)
        while i < n:
            c = s[i]
            if c == "'" and i + 1 < n:
                if s[i + 1:i + 3] in ("re", "ve", "ll"):
                    out.append(s[i:i + 3]); i += 3; continue
                if s[i + 1] in "stmd":
                    out.append(s[i:i + 2]); i += 2; continue
            j = i + 1 if (c == " " and i + 1 < n) else i
            for test in (self.letter, self.number, other):
                if j < n and test(s[j]) and (j == i or c == " "):
                    k = j
                    while k < n and test(s[k]):
                        k += 1
                    out.append(s[i:k]); i = k
                    break
            else:
                k = i
                while k < n and s[k].isspace():
                    k += 1
                if k == n:
                    out.append(s[i:k]); i = k
                elif k - i >= 2:
                    out.append(s[i:k - 1]); i = k - 1
                else:
                    out.append(s[i:k]); i = k
        return out

    def word(self, w):
        parts = list(w)
        while len(parts) > 1:
            best = min(((self.rank.get((parts[q], parts[q + 1]), 1 << 30), q) for q in range(len(parts) - 1)))
            if best[0] == 1 << 30:
                break
            a, b = parts[best[1]], parts[best[1] + 1]
            merged, q = [], 0
            while q < len(parts):
                if q < len(parts) - 1 and parts[q] == a and parts[q + 1] == b:
                    merged.append(a + b); q += 2
                else:
                    merged.append(parts[q]); q += 1
            parts = merged
        return [self.vocab[p] for p in parts]

    def encode(self, s):
        ids = []
        for p in self.pieces(s):
            ids += self.word("".join(self.byte[b] for b in p.encode("utf-8")))
        return ids


# ---- Freivalds over GF(p) ----------------------------------------------------------------------------------------
def dotmod(A, v, p):
    """(A @ v) mod p for A [rows, n] with 0 <= A < p, v [n] with 0 <= v < p: v split in 16-bit halves, int64 exact."""
    vh, vl = v >> 16, v & 0xFFFF
    return (((A @ vh) % p) * 65536 + (A @ vl) % p) % p


ARITH = "f64"                                                              # "int64": dotmod; "f64": exact_mod


def limb_plan(abits, n):
    """Limb widths (la limbs of ka bits for A, limbs of kv bits for v) with ka + kv + ceil(log2 n) <= 52, so every
    float64 partial sum of limb products is an integer below 2^52 and exact."""
    lg = max(1, int(n - 1).bit_length())
    for la in range(1, 8):
        ka = max(1, -(-abits // la))
        kv = 52 - lg - ka
        if kv >= 8:
            return la, ka, kv
    raise ValueError("no limb plan for %d bits, n = %d" % (abits, n))


def exact_mod(A, vecs, primes):
    """[(A @ v) mod p for v, p in zip(vecs, primes)], A int64 [rows, n] of any sign, each v int64 [n] in [0, p).
    A is cut into la limbs (the lower ones in [0, 2^ka), the top one signed, |top| <= 2^ka), every v into limbs in
    [0, 2^kv); all limb columns of all v go into one float64 matrix, so each A limb costs one BLAS product.
    No float rounding can occur: |each product| < 2^(ka+kv), at most 2^lg terms, sum below 2^52."""
    rows, n = A.shape
    la, ka, kv = limb_plan(max(1, int(np.abs(A).max(initial=0)).bit_length()), n)
    lv = -(-31 // kv)
    V = np.empty((n, len(vecs) * lv), dtype=np.float64)
    for j, v in enumerate(vecs):
        for l in range(lv):
            V[:, j * lv + l] = (v >> (kv * l)) & ((1 << kv) - 1)
    out = [np.zeros(rows, dtype=np.int64) for _ in vecs]
    for ja in range(la):
        Aj = A >> (ka * ja)
        if ja < la - 1:
            Aj = Aj & ((1 << ka) - 1)
        R = (Aj.astype(np.float64) @ V).astype(np.int64)
        for j, p in enumerate(primes):
            for l in range(lv):
                out[j] = (out[j] + (R[:, j * lv + l] % p) * pow(2, ka * ja + kv * l, p)) % p
    return out


class Freivalds:
    def __init__(self):
        self.checks = self.macs = self.prep_macs = 0
        self.fail = None

    def vec(self, n, p):
        return np.frombuffer(os.urandom(8 * n), dtype=np.uint64).astype(np.int64) % p    # bias below 2^-32, see text

    def prep(self, W):
        """For W [in, out]: the random r per (prime, rep) and W r mod p."""
        rs = [(p, self.vec(W.shape[1], p)) for p in PRIMES for _ in range(2)]
        self.prep_macs += 4 * W.shape[0] * W.shape[1]
        if ARITH == "f64":
            A = np.asarray(W[0:W.shape[0]], dtype=np.int64)
            return [(p, r, wr) for (p, r), wr in zip(rs, exact_mod(A, [r for _, r in rs], [p for p, _ in rs]))]
        out = []
        for p, r in rs:
            wr = np.empty(W.shape[0], dtype=np.int64)
            for s in range(0, W.shape[0], 8192):
                wr[s:s + 8192] = dotmod(np.asarray(W[s:s + 8192], dtype=np.int64) % p, r, p)
            out.append((p, r, wr))
        return out

    def ok(self, S, X, pr):
        """S [rows, out] claimed = X [rows, in] @ W, with pr = prep(W)."""
        if np.abs(S).max(initial=0) > BOUND:
            return False
        self.checks += 1
        self.macs += 4 * S.shape[0] * (S.shape[1] + X.shape[1])
        if ARITH == "f64":
            ps = [p for p, _, _ in pr]
            lhs = exact_mod(S, [r for _, r, _ in pr], ps)
            rhs = exact_mod(X, [wr for _, _, wr in pr], ps)
            return all(np.array_equal(x, y) for x, y in zip(lhs, rhs))
        good = True
        for p, r, wr in pr:
            if not np.array_equal(dotmod(S % p, r, p), dotmod(X % p, wr, p)):
                good = False
        return good


# ---- the checker ---------------------------------------------------------------------------------------------------
class Checker:
    def __init__(self, W, tables, logits_mode, faults, rng):
        self.W, self.T = W, tables
        self.fv = Freivalds()
        t0 = time.perf_counter()
        self.pr = {}
        for i in range(LAYERS):
            for m in ("self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj", "mlp.gate_proj", "mlp.up_proj", "mlp.down_proj"):
                self.pr[(i, m.split(".")[1][:-5])] = self.fv.prep(W["model.layers.%d.%s.weight" % (i, m)])
        self.logits_mode = logits_mode
        if logits_mode == "freivalds":
            self.pr["logits"] = self.fv.prep(_EmbT(W["model.embed_tokens.weight"]))
        self.prep_s = time.perf_counter() - t0
        self.faults, self.rng = faults, rng
        self.fault_log = []
        self.elem_ops = 0

    def plant(self, kind, layer, S, check):
        """Try `check` on S changed by one at one place; record whether it is rejected."""
        if not self.faults:
            return
        for _ in range(self.faults.get((kind, layer), 0)):
            idx = tuple(int(self.rng.integers(0, d)) for d in S.shape)
            T = S.copy()
            T[idx] += 1 if self.rng.integers(0, 2) else -1
            self.fault_log.append((kind, layer, not check(T)))

    def product(self, kind, key, S, X, layer=LAYERS):
        good = self.fv.ok(S.reshape(-1, S.shape[-1]), X.reshape(-1, X.shape[-1]), self.pr[key])
        self.plant(kind, layer, S, lambda T: self.fv.ok(T.reshape(-1, T.shape[-1]), X.reshape(-1, X.shape[-1]), self.pr[key]))
        if not good and self.fv.fail is None:
            self.fv.fail = kind
        return rnd(S, 16)

    def rms(self, x, g):
        top = np.abs(x).max(-1, keepdims=True)
        assert (top < (1 << 53)).all()
        bl = np.frexp(top.astype(np.float64))[1].astype(np.int64)         # bit length, exact below 2^53
        s = np.maximum(0, bl - 26)
        ms = floordiv(((x >> s) ** 2).sum(-1, keepdims=True), HIDDEN)
        eps = np.array([max(1, round(Fraction(1, 100000) * 2 ** (32 - 2 * k))) for k in range(17)], dtype=np.int64)[s]
        r = int_sqrt(ms + eps)
        y = floordiv(x << (16 - s), r)
        assert (np.abs(y) <= 25 << 16).all()
        self.elem_ops += 8 * x.size
        return rnd(y * np.asarray(g), 16)

    def rope(self, x, pos):
        C = self.T["cos"][pos][:, None]
        S = self.T["sin"][pos][:, None]
        a, b = x[..., :32], x[..., 32:]
        self.elem_ops += 6 * x.size
        return np.concatenate([rnd(a * C - b * S, 20), rnd(b * C + a * S, 20)], -1)

    def exp(self, t):
        E = self.T["exp"]
        k = np.minimum(t >> 8, len(E) - 1)
        r = t & 255
        return (E[k] * (256 - r) + E[np.minimum(k + 1, len(E) - 1)] * r) >> 8

    def silu(self, x):
        Sx = self.T["silu"]
        u = x + (16 << 16)
        top = (len(Sx) - 1) << 8
        uc = np.clip(u, 0, top - 1)
        k, r = uc >> 8, uc & 255
        g = (Sx[k] * (256 - r) + Sx[k + 1] * r) >> 8
        return np.where((u >= 0) & (u < top), g, np.where(u < 0, 0, x))

    def forward(self, ids, pos, kvalid, hint, state):
        W = self.W
        B, L = ids.shape
        x = np.asarray(W["model.embed_tokens.weight"][ids.reshape(-1)], dtype=np.int64).reshape(B, L, HIDDEN)
        for i in range(LAYERS):
            P = "model.layers.%d." % i
            x = clamp(x, "residual")
            h = self.rms(x, W[P + "input_layernorm.weight"]).reshape(B * L, HIDDEN)
            hc = clamp(h, "attention input")
            q = self.product("q", (i, "q"), hint["L%d.q" % i], hc, i).reshape(B, L, HEADS, HEAD).transpose(0, 2, 1, 3)
            k = self.product("k", (i, "k"), hint["L%d.k" % i], hc, i).reshape(B, L, KV, HEAD).transpose(0, 2, 1, 3)
            v = self.product("v", (i, "v"), hint["L%d.v" % i], hc, i).reshape(B, L, KV, HEAD).transpose(0, 2, 1, 3)
            q, k = self.rope(q, pos), self.rope(k, pos)
            ctx = self.attention(i, clamp(q, "q"), clamp(k, "k"), clamp(v, "v"), kvalid, hint, state)
            x = x + self.product("o", (i, "o"), hint["L%d.o" % i], clamp(ctx, "o input"), i).reshape(B, L, HIDDEN)
            x = clamp(x, "residual")
            h = self.rms(x, W[P + "post_attention_layernorm.weight"]).reshape(B * L, HIDDEN)
            hm = clamp(h, "mlp input")
            g = clamp(self.product("gate", (i, "gate"), hint["L%d.gate" % i], hm, i), "gate")
            u = clamp(self.product("up", (i, "up"), hint["L%d.up" % i], hm, i), "up")
            a = rnd(self.silu(g) * u, 16)
            self.elem_ops += 6 * a.size
            x = x + self.product("down", (i, "down"), hint["L%d.down" % i], clamp(a, "down input"), i).reshape(B, L, HIDDEN)
        x = clamp(x, "residual")
        h = clamp(self.rms(x, W["model.norm.weight"]).reshape(B * L, HIDDEN), "logits input")
        if self.logits_mode == "freivalds":
            lg = self.product("logits", "logits", hint["logits"], h)
        else:
            lg = np.empty((B * L, VOCAB), dtype=np.int64)
            hf = h.astype(np.float64)
            for s in range(0, VOCAB, 8192):
                lg[:, s:s + 8192] = rnd((hf @ np.asarray(W["model.embed_tokens.weight"][s:s + 8192], dtype=np.float64).T).astype(np.int64), 16)
            self.fv.macs += B * L * VOCAB * HIDDEN
        return lg.reshape(B, L, VOCAB)

    def attention(self, i, qc, kc, vc, kvalid, hint, state):
        """qc [B, 9, L, 64], kc, vc [B, 3, Lnew, 64] for the new keys only; state[i] keeps K^T r and V r."""
        B, _, L, _ = qc.shape
        st = state.setdefault(i, {"T": 0, "kr": None, "vr": None, "r": None})
        if st["r"] is None:
            st["r"] = [(p, self.fv.vec(4096, p), self.fv.vec(HEAD, p)) for p in PRIMES for _ in range(2)]
            st["kr"] = [np.zeros((B, KV, HEAD), dtype=np.int64) for _ in st["r"]]
            st["vr"] = [np.zeros((B, KV, 0), dtype=np.int64) for _ in st["r"]]
            st["v"] = np.zeros((B, KV, 0, HEAD), dtype=np.int64)
        T0, n = st["T"], kc.shape[2]
        for j, (p, rT, r64) in enumerate(st["r"]):                         # keys arrive: update K^T r and V r
            st["kr"][j] = (st["kr"][j] + ((kc % p) * rT[T0:T0 + n][None, None, :, None] % p).sum(2)) % p
            st["vr"][j] = np.concatenate([st["vr"][j], dotmod((vc % p).reshape(-1, HEAD), r64, p).reshape(B, KV, n)], 2)
        st["T"] = T = T0 + n
        S = hint["L%d.s" % i]                                                # [B, 3, 3, L, T]
        q5 = qc.reshape(B, KV, HEADS // KV, L, HEAD)

        def ok_scores(Sx):
            if np.abs(Sx).max() > BOUND:
                return False
            good = True
            for j, (p, rT, r64) in enumerate(st["r"]):
                lhs = dotmod(Sx.reshape(-1, T) % p, rT[:T], p).reshape(B, KV, HEADS // KV, L)
                rhs = (((q5 % p) * st["kr"][j][:, :, None, None, :]) % p).sum(-1) % p
                good &= np.array_equal(lhs, rhs)
            return good
        good = ok_scores(S)
        self.fv.checks += 1
        self.fv.macs += 4 * (S.size + q5.size)
        self.plant("scores", i, S, ok_scores)
        if not good and self.fv.fail is None:
            self.fv.fail = "scores layer %d" % i
        key = kvalid[:, None, None]
        m = np.where(key, S, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - S, 0) >> 19
        e = np.where(key, self.exp(t), 0)
        pr = floordiv(e << 16, e.sum(-1, keepdims=True))
        self.elem_ops += 8 * S.size
        C = hint["L%d.ctx" % i]                                              # [B, 3, 3, L, 64]

        def ok_ctx(Cx):
            if np.abs(Cx).max() > BOUND:
                return False
            good = True
            for j, (p, rT, r64) in enumerate(st["r"]):
                lhs = dotmod(Cx.reshape(-1, HEAD) % p, r64, p).reshape(B, KV, HEADS // KV, L)
                rhs = ((pr * st["vr"][j][:, :, None, None, :]) % p).sum(-1) % p
                good &= np.array_equal(lhs, rhs)
            return good
        good = ok_ctx(C)
        self.fv.checks += 1
        self.fv.macs += 4 * (C.size + pr.size)
        self.plant("ctx", i, C, ok_ctx)
        if not good and self.fv.fail is None:
            self.fv.fail = "ctx layer %d" % i
        return rnd(C, 16).reshape(B, HEADS, L, HEAD).transpose(0, 2, 1, 3).reshape(B * L, HIDDEN)


class _EmbT:
    """E^T [576, V] as row blocks of E [V, 576], for prep()."""
    def __init__(self, E):
        self.E, self.shape = E, (E.shape[1], E.shape[0])

    def __getitem__(self, sl):
        if not hasattr(self, "T"):
            self.T = np.asarray(self.E, dtype=np.int64).T                  # converted once, not once per (prime, r)
        return self.T[sl]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exact", type=Path, required=True, help="proofs/exact-llm (pins.json, tables/)")
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--wdir", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--logits", default="freivalds", choices=("freivalds", "direct"))
    ap.add_argument("--faults", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--grid", action="store_true", help="also one planted fault at every (kind, layer), at a random call")
    ap.add_argument("--claim-token", help="B:T:ID, replace claimed token T of row B by ID (control)")
    ap.add_argument("--arith", default="f64", choices=("f64", "int64"), help="mod-p products: float64 limbs or int64")
    ap.add_argument("--session", type=int, nargs="*", help="batches to check in one session (W r prepared once): "
                    "for each, the prover (trace.py, another process, never given r) writes --trace, then it is checked and deleted")
    a = ap.parse_args()
    global ARITH
    ARITH = a.arith
    pins = json.load(open(a.exact / "pins.json"))
    pin = pins["models"]["SmolLM2-135M"] if "models" in pins else pins["model"]   # the layout after #90, and before
    for name, digest in pin["files"].items():
        if name != "config.json":
            assert sha(a.cache / "model" / name) == digest, name
    assert sha(a.cache / "data" / pins["prompts"]["file"]) == pins["prompts"]["sha256"]
    W = weights(a.cache / "model" / "model.safetensors", a.wdir)
    tab = lambda n: np.array([int(l) for l in open(a.exact / "tables" / n) if not l.startswith("#")], dtype=np.int64)
    tables = {"exp": tab("exp.txt"), "silu": tab("silu.txt"), "cos": tab("cos.txt").reshape(512, 32), "sin": tab("sin.txt").reshape(512, 32)}
    tok = BPE(a.cache / "model" / "tokenizer.json")
    rows = [json.loads(l) for l in gzip.open(a.cache / "data" / pins["prompts"]["file"], "rt", encoding="utf-8")]
    if a.session is None:
        rec, good = check_trace(a, None, W, tables, tok, rows, a.trace)
        print(json.dumps(rec))
        raise SystemExit(0 if good else 1)
    import shutil
    import subprocess
    t0 = time.perf_counter()
    ck = Checker(W, tables, a.logits, None, np.random.default_rng(a.seed))   # r drawn here, once
    prep_s, total, ok_all, prover_s = time.perf_counter() - t0, 0.0, True, 0.0
    env = dict(os.environ, EXACT_LLM_CACHE=str(a.cache))
    for b in a.session:
        tp = time.perf_counter()
        r = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("trace.py")), "--exact", str(a.exact),
                            "--batch-index", str(b), "--out", str(a.trace)], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr[-500:]
        prover_s += time.perf_counter() - tp
        ck.fv = Freivalds()                                                  # per-trace counters; r and W r stay in ck.pr
        ck.elem_ops, ck.fault_log = 0, []
        rec, good = check_trace(a, ck, W, tables, tok, rows, a.trace)
        total += rec["check_s"]
        ok_all &= good
        print(json.dumps(rec), flush=True)
        shutil.rmtree(a.trace)
    print(json.dumps({"session": a.session, "arith": ARITH, "logits": a.logits, "prep_s": round(prep_s, 2),
                      "check_s_sum": round(total, 2), "session_check_s": round(prep_s + total, 2),
                      "prover_s_excluded": round(prover_s, 2), "all_accept": ok_all}))
    raise SystemExit(0 if ok_all else 1)


def check_trace(a, ck, W, tables, tok, rows, trace):
    """One trace; ck None: a new Checker (W r prepared for this trace alone)."""
    claim = json.load(open(trace / "claim.json"))
    texts = [r["sentence1"] for r in rows[:64]][claim["prompts"][0]:claim["prompts"][1]]
    cont_claim = [list(c) for c in claim["continuations"]]
    if a.claim_token:
        b, t, v = (int(z) for z in a.claim_token.split(":"))
        cont_claim[b][t] = v
    t_all = time.perf_counter()
    rng = np.random.default_rng(a.seed)
    calls = len(list(trace.glob("call_*.npz")))
    # faults: spread N over the kinds and the calls of this batch
    kinds = ["q", "k", "v", "o", "gate", "up", "down", "scores", "ctx"] + (["logits"] if a.logits == "freivalds" else [])
    per = {}                                                               # (call, kind, layer) -> count
    for n in range(a.faults):
        kind = kinds[n % len(kinds)]
        key = (int(rng.integers(0, calls)), kind, LAYERS if kind == "logits" else int(rng.integers(0, LAYERS)))
        per[key] = per.get(key, 0) + 1
    if a.grid:
        for kind in kinds:
            for layer in ([LAYERS] if kind == "logits" else range(LAYERS)):
                key = (int(rng.integers(0, calls)), kind, layer)
                per[key] = per.get(key, 0) + 1
    if ck is None:
        ck = Checker(W, tables, a.logits, None, rng)
        prep_s = ck.prep_s
    else:
        ck.rng, prep_s = rng, 0.0
    t_loop = time.perf_counter()
    enc = [tok.encode(t) for t in texts]
    B, Lmax = len(enc), max(len(e) for e in enc)
    lens = np.array([len(e) for e in enc])
    ids = np.zeros((B, Lmax), dtype=np.int64)
    for b, e in enumerate(enc):
        ids[b, :len(e)] = e
    pos = np.broadcast_to(np.arange(Lmax), (B, Lmax))
    idx = np.arange(Lmax)
    kvalid = (idx[None, None, :] <= idx[None, :, None]) & (idx[None, None, :] < lens[:, None, None])
    state, cont, verdict = {}, [[] for _ in range(B)], None
    gen = len(cont_claim[0])
    for c in range(gen):
        hint = np.load(trace / ("call_%d.npz" % c))
        hint = {k: hint[k] for k in hint.files}
        ck.faults = {(kind, layer): m for (cc, kind, layer), m in per.items() if cc == c}
        lg = ck.forward(ids, pos, kvalid, hint, state)
        if ck.fv.fail is not None:
            verdict = "reject: call %d, %s" % (c, ck.fv.fail)
            break
        last = lens - 1 if c == 0 else np.zeros(B, dtype=np.int64)
        nxt = np.array([int(np.argmax(lg[b, last[b]])) for b in range(B)])
        for b in range(B):
            cont[b].append(int(nxt[b]))
            if cont[b][-1] != cont_claim[b][c]:
                verdict = verdict or "reject: call %d, row %d token %d claimed, %d computed" % (c, b, cont_claim[b][c], cont[b][-1])
        if verdict:
            break
        T = Lmax + c + 1
        tidx = np.arange(T)
        kvalid = ((tidx[None] < lens[:, None]) | ((tidx[None] >= Lmax) & (tidx[None] <= Lmax + c)))[:, None, :]
        ids, pos = nxt[:, None], (lens + c)[:, None]
    dt = time.perf_counter() - t_all
    caught = sum(1 for _, _, r in ck.fault_log if r)
    by = {}
    pairs = sorted({(kind, layer) for kind, layer, r in ck.fault_log if r})
    for kind, layer, r in ck.fault_log:
        by.setdefault(kind, [0, 0])
        by[kind][0] += 1
        by[kind][1] += r
    rec = {"batch": claim["batch"], "verdict": verdict or "accept", "logits": a.logits, "arith": ARITH, "calls": c + 1,
           "check_s": round(dt, 2), "prep_s": round(prep_s, 2), "loop_s": round(time.perf_counter() - t_loop, 2),
           "freivalds_checks": ck.fv.checks, "check_macs": ck.fv.macs, "prep_macs": ck.fv.prep_macs, "elem_ops": ck.elem_ops,
           "faults": len(ck.fault_log), "caught": caught, "by_kind": by, "pairs_caught": len(pairs), "tokens": int(lens.sum()) + B * (gen - 1)}
    return rec, verdict is None and caught == len(ck.fault_log)


if __name__ == "__main__":
    main()
