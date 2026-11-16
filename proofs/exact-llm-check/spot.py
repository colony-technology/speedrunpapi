"""Commit to a trace with a Merkle root and check k places opened at random, each place checked alone.

    PY spot.py MODE --exact DIR --cache CACHE --wdir W --trace TRACE_DIR [options]
      commit                      leaves and tree from the trace (trace.py --resid); root, sizes, time -> JSON
      map    [--claim-token B:T:ID] every unit checked directly from the trace: the units that fail -> JSON
      faults --n N --seed S       N single-integer changes (one product leaf, one integer, +-1): failing units per change
      spot   --k K --reps R       the protocol: k units drawn after the root, opened with paths, checked alone

Leaves (one per token, layer and item, in a public order the checker computes from the prompts and the claim):
  for every token t (prompt tokens and fed-back generated tokens) and layer i < 30:
    r0 (the clamped residual entering layer i), q, k, v, s (scores of t against its valid keys), ctx, o, gate, up, down
    (each product as its exact sum before the rounding shift, as in trace.py);
  for every token: final (the clamped residual after layer 29); for the 384 tokens whose logits pick a claimed token:
  logits.  Leaf bytes: (call, row, slot, code) as four int32, then the int64 values.  Leaf hash sha256(0x00 || bytes),
  node sha256(0x01 || left || right), padding leaves sha256(0x02), to a power of two.

Units (what an opened place is):
  (t, i), i < 30: opened leaves r0, q, k, v, s, ctx, o, gate, up, down of (t, i); r0 of (t, i + 1), or final(t) when
  i = 29; k and v of (tau, i) for every other key tau of t.  The checker, from these alone: for i = 0, r0 equals the
  clamped embedding of t's token (the prompt's, or the claimed one fed back); RMS norm of r0; q, k, v equal the
  products (computed directly, exact); scores equal q K^T over the opened keys (rotary step at each key's position);
  softmax; ctx equals p V; o; residual; RMS; gate, up; SiLU; down; the next residual equals the opened one.
  logits unit t: final(t) and logits(t): logits equal h E^T, and their argmax equals the claimed token.
If every unit passes, induction over layers and tokens gives the honest run: so any wrong claimed token leaves at least
one failing unit, and k units drawn uniformly without replacement find one of F failing units with probability
1 - C(U - F, k) / C(U, k).
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check", HERE / "check.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
LAYERS, HIDDEN, HEADS, KV, HEAD, FF, VOCAB = C.LAYERS, C.HIDDEN, C.HEADS, C.KV, C.HEAD, C.FF, C.VOCAB
ITEMS = ["r0", "q", "k", "v", "s", "ctx", "o", "gate", "up", "down"]
PRODUCTS = ["q", "k", "v", "s", "ctx", "o", "gate", "up", "down", "logits"]
WIDTH = {"r0": HIDDEN, "q": HIDDEN, "k": KV * HEAD, "v": KV * HEAD, "o": HIDDEN, "gate": FF, "up": FF, "down": HIDDEN,
         "final": HIDDEN, "logits": VOCAB, "ctx": HEADS * HEAD}
H0, H1, PAD = b"\x00", b"\x01", hashlib.sha256(b"\x02").digest()


# ---- public layout ---------------------------------------------------------------------------------------------------
class Layout:
    def __init__(self, enc, cont):
        self.B, self.lens, self.Lmax, self.gen = len(enc), [len(e) for e in enc], max(len(e) for e in enc), len(cont[0])
        self.enc, self.cont = enc, cont
        self.tokens = [(0, b, l) for b in range(self.B) for l in range(self.lens[b])]
        self.tokens += [(c, b, self.Lmax + c - 1) for c in range(1, self.gen) for b in range(self.B)]
        self.leaves = []
        for t in self.tokens:
            for i in range(LAYERS):
                for it in ITEMS:
                    self.leaves.append((t, i, it))
            self.leaves.append((t, LAYERS, "final"))
            if self.claimed(t) is not None:
                self.leaves.append((t, LAYERS + 1, "logits"))
        self.index = {k: n for n, k in enumerate(self.leaves)}
        self.units = [(t, i) for t in self.tokens for i in range(LAYERS)] + [(t, "logits") for t in self.tokens if self.claimed(t) is not None]

    def pos(self, t):
        c, b, slot = t
        return slot if c == 0 else self.lens[b] + c - 1

    def token_id(self, t):
        c, b, slot = t
        return self.enc[b][slot] if c == 0 else self.cont[b][c - 1]

    def claimed(self, t):
        c, b, slot = t
        if c == 0:
            return self.cont[b][0] if slot == self.lens[b] - 1 else None
        return self.cont[b][c]

    def keys(self, t):
        """The tokens t attends to, in slot order (t itself last)."""
        c, b, slot = t
        if c == 0:
            return [(0, b, s) for s in range(slot + 1)]
        return [(0, b, s) for s in range(self.lens[b])] + [(cc, b, self.Lmax + cc - 1) for cc in range(1, c + 1)]

    def code(self, i, it):
        return i * 16 + (ITEMS.index(it) if it in ITEMS else 0)

    def shape(self, key):
        t, i, it = key
        if it == "s":
            return (HEADS, len(self.keys(t)))
        if it == "ctx":
            return (HEADS, HEAD)
        return (WIDTH[it],)

    def opened(self, unit):
        t, i = unit
        if i == "logits":
            return [(t, LAYERS, "final"), (t, LAYERS + 1, "logits")]
        keys = [(t, i, it) for it in ITEMS]
        keys.append((t, i + 1, "r0") if i + 1 < LAYERS else (t, LAYERS, "final"))
        for tau in self.keys(t)[:-1]:
            keys += [(tau, i, "k"), (tau, i, "v")]
        return keys


def leaf_bytes(lay, key, arr):
    (c, b, slot), i, it = key
    return struct.pack("<4i", c, b, slot, lay.code(i, it)) + np.ascontiguousarray(arr, dtype="<i8").tobytes()


# ---- reading leaves from a trace (prover side, and the map) ----------------------------------------------------------
class TraceLeaves:
    def __init__(self, lay, trace):
        self.lay, self.trace, self.cache, self.over = lay, trace, {}, {}

    def arr(self, c, name):
        k = (c, name)
        if k not in self.cache:
            if len(self.cache) > 4000:
                self.cache.clear()
            with np.load(self.trace / ("call_%d.npz" % c)) as z:
                self.cache[k] = z[name]
        return self.cache[k]

    def get(self, key):
        if key in self.over:
            return self.over[key]
        lay = self.lay
        (c, b, slot), i, it = key
        L = lay.Lmax if c == 0 else 1
        l = slot if c == 0 else 0
        if it == "r0":
            return self.arr(c, "L%d.r0" % i)[b, l]
        if it == "final":
            return self.arr(c, "final")[b, l]
        if it == "logits":
            return self.arr(c, "logits")[b * L + l]
        if it == "s":
            slots = [s for (_, _, s) in lay.keys((c, b, slot))]
            return self.arr(c, "L%d.s" % i)[b, :, :, l][:, :, slots].reshape(HEADS, -1)
        if it == "ctx":
            return self.arr(c, "L%d.ctx" % i)[b, :, :, l].reshape(HEADS, HEAD)
        return self.arr(c, "L%d.%s" % (i, it))[b * L + l]


# ---- Merkle tree -------------------------------------------------------------------------------------------------------
def build_tree(leaf_hashes):
    n = 1 << max(1, (len(leaf_hashes) - 1).bit_length())
    level = list(leaf_hashes) + [PAD] * (n - len(leaf_hashes))
    levels = [level]
    while len(level) > 1:
        level = [hashlib.sha256(H1 + level[j] + level[j + 1]).digest() for j in range(0, len(level), 2)]
        levels.append(level)
    return levels


def path(levels, idx):
    out = []
    for lv in levels[:-1]:
        out.append(lv[idx ^ 1])
        idx >>= 1
    return out


def verify(root, idx, data, sibs):
    h = hashlib.sha256(H0 + data).digest()
    for d, s in enumerate(sibs):
        h = hashlib.sha256(H1 + s + h).digest() if (idx >> d) & 1 else hashlib.sha256(H1 + h + s).digest()
    return h == root


# ---- unit check (checker side; uses only get(), the public weights and tables) ---------------------------------------
class UnitChecker:
    def __init__(self, W, tables, lay):
        self.W, self.lay = W, lay
        self.el = C.Checker.__new__(C.Checker)                                # for its element-wise methods only
        self.el.T, self.el.elem_ops = tables, 0
        self.layer_cache, self.Ef, self.kv_cache = (None, None), None, {}

    def mats(self, i):
        if self.layer_cache[0] != i:
            P = "model.layers.%d." % i
            self.layer_cache = (i, {m: np.asarray(self.W[P + n + ".weight"], dtype=np.float64) for m, n in (
                ("q", "self_attn.q_proj"), ("k", "self_attn.k_proj"), ("v", "self_attn.v_proj"), ("o", "self_attn.o_proj"),
                ("gate", "mlp.gate_proj"), ("up", "mlp.up_proj"), ("down", "mlp.down_proj"))})
        return self.layer_cache[1]

    def prod(self, x, Wf):
        return (x.astype(np.float64) @ Wf).astype(np.int64)                  # exact: every partial sum below 2^53

    def rms(self, x, g):
        return self.el.rms(x[None], g)[0]

    def keyval(self, get, tau, i, cache):
        k = (tau, i)
        if cache and k in self.kv_cache:
            return self.kv_cache[k]
        kk = C.rnd(get((tau, i, "k")), 16).reshape(1, KV, 1, HEAD)
        kk = C.clamp(self.el.rope(kk, np.array([[self.lay.pos(tau)]])), "k").reshape(KV, HEAD)
        vv = C.clamp(C.rnd(get((tau, i, "v")), 16).reshape(KV, HEAD), "v")
        if cache:
            self.kv_cache[k] = (kk, vv)
        return kk, vv

    def check(self, get, unit, cache=False):
        """True if the unit passes; else the name of the first value that does not check."""
        lay, W = self.lay, self.W
        t, i = unit
        if i == "logits":
            f = get((t, LAYERS, "final"))
            h = C.clamp(self.rms(f, W["model.norm.weight"]), "logits input")
            if self.Ef is None:
                self.Ef = np.asarray(W["model.embed_tokens.weight"], dtype=np.float64)
            lg = get((t, LAYERS + 1, "logits"))
            if not np.array_equal(self.prod(h, self.Ef.T), lg):
                return "logits"
            return True if int(np.argmax(C.rnd(lg, 16))) == lay.claimed(t) else "claimed token"
        P = "model.layers.%d." % i
        M = self.mats(i)
        x = get((t, i, "r0"))
        if i == 0 and not np.array_equal(x, C.clamp(np.asarray(W["model.embed_tokens.weight"][lay.token_id(t)], dtype=np.int64), "residual")):
            return "embedding"
        hc = C.clamp(self.rms(x, W[P + "input_layernorm.weight"]), "attention input")
        for m in ("q", "k", "v"):
            if not np.array_equal(self.prod(hc, M[m]), get((t, i, m))):
                return m
        q = C.rnd(get((t, i, "q")), 16).reshape(1, HEADS, 1, HEAD)
        qc = C.clamp(self.el.rope(q, np.array([[lay.pos(t)]])), "q").reshape(HEADS, HEAD)
        kv = [self.keyval(get, tau, i, cache) for tau in lay.keys(t)]
        K = np.stack([a for a, _ in kv], 1)                                   # [3, T, 64]
        V = np.stack([b for _, b in kv], 1)
        s = np.concatenate([qc[g * 3:(g + 1) * 3] @ K[g].T for g in range(KV)], 0)   # [9, T], int64
        S = get((t, i, "s"))
        if not np.array_equal(s, S):
            return "scores"
        tt = (S.max(-1, keepdims=True) - S) >> 19
        e = self.el.exp(tt)
        p = C.floordiv(e << 16, e.sum(-1, keepdims=True))
        ctx = np.concatenate([p[g * 3:(g + 1) * 3] @ V[g] for g in range(KV)], 0)  # [9, 64]
        Cx = get((t, i, "ctx"))
        if not np.array_equal(ctx, Cx):
            return "ctx"
        oc = C.clamp(C.rnd(Cx, 16).reshape(HIDDEN), "o input")
        if not np.array_equal(self.prod(oc, M["o"]), get((t, i, "o"))):
            return "o"
        x1 = C.clamp(x + C.rnd(get((t, i, "o")), 16), "residual")
        hm = C.clamp(self.rms(x1, W[P + "post_attention_layernorm.weight"]), "mlp input")
        for m in ("gate", "up"):
            if not np.array_equal(self.prod(hm, M[m]), get((t, i, m))):
                return m
        g = C.clamp(C.rnd(get((t, i, "gate")), 16), "gate")
        u = C.clamp(C.rnd(get((t, i, "up")), 16), "up")
        a = C.clamp(C.rnd(self.el.silu(g) * u, 16), "down input")
        if not np.array_equal(self.prod(a, M["down"]), get((t, i, "down"))):
            return "down"
        nxt = C.clamp(x1 + C.rnd(get((t, i, "down")), 16), "residual")
        want = get((t, i + 1, "r0")) if i + 1 < LAYERS else get((t, LAYERS, "final"))
        return True if np.array_equal(nxt, want) else "next residual"


# ---- setup -------------------------------------------------------------------------------------------------------------
def setup(a):
    import gzip
    pins = json.load(open(a.exact / "pins.json"))
    W = C.weights(a.cache / "model" / "model.safetensors", a.wdir)
    tab = lambda n: np.array([int(l) for l in open(a.exact / "tables" / n) if not l.startswith("#")], dtype=np.int64)
    tables = {"exp": tab("exp.txt"), "silu": tab("silu.txt"), "cos": tab("cos.txt").reshape(512, 32), "sin": tab("sin.txt").reshape(512, 32)}
    tok = C.BPE(a.cache / "model" / "tokenizer.json")
    claim = json.load(open(a.trace / "claim.json"))
    rows = [json.loads(l) for l in gzip.open(a.cache / "data" / pins["prompts"]["file"], "rt", encoding="utf-8")]
    texts = [r["sentence1"] for r in rows[:64]][claim["prompts"][0]:claim["prompts"][1]]
    cont = [list(c) for c in claim["continuations"]]
    if getattr(a, "claim_token", None):
        b, t, v = (int(z) for z in a.claim_token.split(":"))
        cont[b][t] = v
    return W, tables, Layout([tok.encode(t) for t in texts], cont), claim


def commit(lay, trace):
    """Prover: leaf hashes in the public order, the tree, sizes."""
    tl = TraceLeaves(lay, trace)
    hs, nbytes = [], 0
    for key in lay.leaves:
        d = leaf_bytes(lay, key, tl.get(key))
        nbytes += len(d)
        hs.append(hashlib.sha256(H0 + d).digest())
    return build_tree(hs), nbytes, tl


def p_catch(U, F, k):
    if F == 0:
        return 0.0
    if k > U - F:
        return 1.0
    return 1.0 - math.exp(math.lgamma(U - F + 1) - math.lgamma(U - F - k + 1) - math.lgamma(U + 1) + math.lgamma(U - k + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("commit", "map", "faults", "spot"))
    ap.add_argument("--exact", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--wdir", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--claim-token")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--k", type=int, nargs="*", default=[16, 64, 256])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    W, tables, lay, claim = setup(a)
    U = len(lay.units)
    base = {"mode": a.mode, "label": a.label, "batch": claim["batch"], "tokens": len(lay.tokens), "leaves": len(lay.leaves), "units": U}

    if a.mode == "commit":
        t0 = time.perf_counter()
        levels, nbytes, _ = commit(lay, a.trace)
        print(json.dumps({**base, "root": levels[-1][0].hex(), "depth": len(levels) - 1, "leaf_bytes": nbytes,
                          "commit_s": round(time.perf_counter() - t0, 2)}))
        return

    uc = UnitChecker(W, tables, lay)
    if a.mode == "map":
        tl = TraceLeaves(lay, a.trace)
        t0 = time.perf_counter()
        fails = {}
        for u in sorted(lay.units, key=lambda u: (LAYERS + 1 if u[1] == "logits" else u[1], u[0])):
            r = uc.check(tl.get, u, cache=True)
            if r is not True:
                fails.setdefault(r, []).append([list(u[0]), u[1]])
        F = sum(len(v) for v in fails.values())
        print(json.dumps({**base, "claim_token": a.claim_token, "map_s": round(time.perf_counter() - t0, 2), "failing_units": F,
                          "by_reason": {k: len(v) for k, v in fails.items()},
                          "failing_layers": sorted({u[1] for v in fails.values() for u in v}, key=str),
                          "p_catch": {str(k): round(p_catch(U, F, k), 6) for k in a.k}, "first": {k: v[:3] for k, v in fails.items()}}))
        return

    if a.mode == "faults":
        tl = TraceLeaves(lay, a.trace)
        rng = np.random.default_rng(a.seed)
        openers = {}
        for u in lay.units:
            for key in lay.opened(u):
                openers.setdefault(key, []).append(u)
        by_item = {it: [k for k in lay.leaves if k[2] == it] for it in PRODUCTS}
        res, t0 = [], time.perf_counter()
        for n in range(a.n):
            it = PRODUCTS[n % len(PRODUCTS)]
            key = by_item[it][int(rng.integers(0, len(by_item[it])))]
            arr = np.array(tl.get(key), dtype=np.int64)
            idx = tuple(int(rng.integers(0, d)) for d in arr.shape)
            arr[idx] += 1 if rng.integers(0, 2) else -1
            tl.over = {key: arr}
            F = sum(1 for u in openers[key] if uc.check(tl.get, u) is not True)
            tl.over = {}
            res.append({"leaf": [list(key[0]), key[1], key[2]], "openers": len(openers[key]), "failing_units": F})
        Fs = [r["failing_units"] for r in res]
        by = {}
        for r in res:
            by.setdefault(r["leaf"][2], []).append(r["failing_units"])
        print(json.dumps({**base, "faults": a.n, "faults_s": round(time.perf_counter() - t0, 2),
                          "caught_if_all_opened": sum(1 for f in Fs if f > 0),
                          "failing_units_min_median_max": [min(Fs), sorted(Fs)[len(Fs) // 2], max(Fs)],
                          "failing_units_by_item": {k: [min(v), max(v)] for k, v in by.items()},
                          "p_catch_mean": {str(k): round(sum(p_catch(U, f, k) for f in Fs) / len(Fs), 6) for k in a.k}}))
        return

    # spot: the protocol.  Prover commits; checker draws units after the root; prover opens; checker verifies alone.
    t0 = time.perf_counter()
    levels, nbytes, tl = commit(lay, a.trace)
    commit_s, root = time.perf_counter() - t0, levels[-1][0]
    out = []
    for k in a.k:
        for rep in range(a.reps):
            draw = np.random.default_rng(int.from_bytes(os.urandom(16), "little")).choice(U, size=k, replace=False)
            units = [lay.units[int(j)] for j in draw]
            tp = time.perf_counter()                                          # prover: the opening
            want = sorted({lay.index[key] for u in units for key in lay.opened(u)})
            blob = bytearray()
            for idx in want:
                d = leaf_bytes(lay, lay.leaves[idx], tl.get(lay.leaves[idx]))
                blob += struct.pack("<II", idx, len(d)) + d + b"".join(path(levels, idx))
            prover_s = time.perf_counter() - tp
            tc = time.perf_counter()                                          # checker: from root, layout, blob only
            depth, got, off, bad_path = len(levels) - 1, {}, 0, 0
            while off < len(blob):
                idx, ln = struct.unpack_from("<II", blob, off)
                d = bytes(blob[off + 8:off + 8 + ln])
                sibs = [bytes(blob[off + 8 + ln + 32 * j:off + 8 + ln + 32 * (j + 1)]) for j in range(depth)]
                off += 8 + ln + 32 * depth
                key = lay.leaves[idx]
                if not verify(root, idx, d, sibs) or d[:16] != struct.pack("<4i", *key[0], lay.code(key[1], key[2])):
                    bad_path += 1
                    continue
                got[key] = np.frombuffer(d[16:], dtype="<i8").reshape(lay.shape(key))
            uc.kv_cache = {}
            results = [uc.check(lambda key: got[key], u) for u in sorted(units, key=lambda u: (LAYERS + 1 if u[1] == "logits" else u[1], u[0]))]
            check_s = time.perf_counter() - tc
            fails = [r for r in results if r is not True]
            out.append({"k": k, "rep": rep, "leaves_opened": len(want), "bytes_sent": len(blob) + 32, "prover_open_s": round(prover_s, 3),
                        "check_s": round(check_s, 3), "bad_paths": bad_path, "failing": len(fails), "reasons": sorted(set(fails))})
    print(json.dumps({**base, "root": root.hex(), "depth": len(levels) - 1, "leaf_bytes": nbytes, "commit_s": round(commit_s, 2), "runs": out}))


if __name__ == "__main__":
    main()
