"""Exact inference for a language model: HuggingFaceTB/SmolLM2-135M in integer arithmetic.

The method of proofs/exact-embeddings on a decoder. Every tensor is an integer array with a power-of-two scale;
element-wise work is NumPy int64; the only floating-point operation is matrix multiplication by the machine's
float64 BLAS on integer-valued arrays whose partial sums stay below 2^53 (bounds.py). exp, SiLU and the rotary cos
and sin are integer tables (tables/, make_tables.py). The output is the next-token logits at every position, as
integers at scale 2^-16, and greedy continuations computed from them.

The same file holds the pinned downloads, a byte-level BPE tokenizer in plain Python, a plain float32 forward pass
of the same weights (the baseline), an onnxruntime baseline on the onnx-community export, and the evaluation.

usage:
  python exact_llm.py check                       digests, both hashes against expected.sha256, baselines, distance
  python exact_llm.py hash --engine exact|float32|onnx [--batch N] [--threads N]
"""
import gzip
import hashlib
import json
import math
import os
import struct
import sys
import unicodedata
import urllib.request
from fractions import Fraction

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = json.load(open(os.path.join(HERE, "pins.json")))
CACHE = os.environ.get("EXACT_LLM_CACHE", os.path.join(HERE, ".cache"))

LAYERS, HIDDEN, HEADS, KV, HEAD, FF, VOCAB = 30, 576, 9, 3, 64, 1536, 49152
THETA, EPS = 100000, Fraction("1e-05")          # config.json: rope_theta, rms_norm_eps
GEN = 48                                        # greedy continuation length


# ---- downloads ------------------------------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, path, digest):
    if not (os.path.exists(path) and sha256_file(path) == digest):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "exact-llm"})
        with urllib.request.urlopen(req) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)
    got = sha256_file(path)
    if got != digest:
        raise SystemExit("digest mismatch for %s: %s, pinned %s" % (path, got, digest))
    return path


def model_file(name):
    m = PINS["model"]
    return fetch("https://huggingface.co/%s/resolve/%s/%s" % (m["repo"], m["revision"], name),
                 os.path.join(CACHE, "model", name), m["files"][name])


def prompts():
    p = PINS["prompts"]
    path = fetch("https://huggingface.co/datasets/%s/resolve/%s/%s" % (p["repo"], p["revision"], p["file"]),
                 os.path.join(CACHE, "data", p["file"]), p["sha256"])
    rows = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    return [r["sentence1"] for r in rows[:64]]


def text():
    t = PINS["text"]
    return open(fetch(t["url"], os.path.join(CACHE, "data", "input.txt"), t["sha256"]), encoding="utf-8").read()


# ---- safetensors, parsed here; bfloat16 widened to float32 exactly (the 16 bits become the high half) -------------
def iter_safetensors(path, names=None):
    """Yield (name, float32 array) one tensor at a time, reading only that tensor's bytes."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n).decode("utf-8"))
        header.pop("__metadata__", None)
        for name, t in header.items():
            if names is not None and name not in names:
                continue
            assert t["dtype"] == "BF16", (name, t["dtype"])
            b, e = t["data_offsets"]
            f.seek(8 + n + b)
            raw = np.frombuffer(f.read(e - b), dtype="<u2")
            yield name, (raw.astype(np.uint32) << 16).view(np.float32).reshape(t["shape"])


def read_safetensors(path, names=None):
    return dict(iter_safetensors(path, names))


# ---- tokenizer: byte-level BPE, from the pinned tokenizer.json --------------------------------------------------
# Pre-tokenizer: Digits (each digit alone), then ByteLevel with the GPT-2 pattern
#   's|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+
# written out below with unicodedata (Python's re has no \p{L}). \s is the Unicode White_Space set.
WHITE = set("\t\n\x0b\x0c\r \x85\xa0     　") | {chr(c) for c in range(0x2000, 0x200B)}


def _L(c):
    return unicodedata.category(c)[0] == "L"


def _N(c):
    return unicodedata.category(c)[0] == "N"


def _other(c):
    return c not in WHITE and not _L(c) and not _N(c)


def gpt2_split(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "'":
            hit = next((suf for suf in ("s", "t", "re", "ve", "m", "ll", "d") if s.startswith(suf, i + 1)), None)
            if hit:
                out.append("'" + hit)
                i += 1 + len(hit)
                continue
        done = False
        for cls in (_L, _N, _other):
            j = i + 1 if (c == " " and i + 1 < n and cls(s[i + 1])) else i
            if cls(s[j]):
                k = j
                while k < n and cls(s[k]):
                    k += 1
                out.append(s[i:k])
                i, done = k, True
                break
        if done:
            continue
        k = i                                   # c is whitespace
        while k < n and s[k] in WHITE:
            k += 1
        if k == n or k - i == 1:
            out.append(s[i:k])
            i = k
        else:
            out.append(s[i:k - 1])              # \s+(?!\S): leave the last one for the next word
            i = k - 1
    return out


def digits_split(s):
    out, cur = [], ""
    for c in s:
        if _N(c):
            if cur:
                out.append(cur)
                cur = ""
            out.append(c)
        else:
            cur += c
    if cur:
        out.append(cur)
    return out


def _byte_encoder():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + list(range(ord("\xae"), 256))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {b: chr(c) for b, c in zip(bs, cs)}


class Tokenizer:
    def __init__(self, path):
        t = json.load(open(path, encoding="utf-8"))
        assert t["normalizer"] is None and t["post_processor"] is None and t["model"]["type"] == "BPE"
        self.vocab = t["model"]["vocab"]
        self.rank = {tuple(m.split(" ")) if isinstance(m, str) else tuple(m): i for i, m in enumerate(t["model"]["merges"])}
        self.added = sorted((a["content"] for a in t["added_tokens"]), key=len, reverse=True)
        self.added_id = {a["content"]: a["id"] for a in t["added_tokens"]}
        self.enc = _byte_encoder()
        self.memo = {}

    def bpe(self, word):
        if word in self.memo:
            return self.memo[word]
        parts = list(word)
        while len(parts) > 1:
            best = min(((self.rank.get((parts[i], parts[i + 1]), 1 << 30), i) for i in range(len(parts) - 1)))
            if best[0] == 1 << 30:
                break
            a, b = parts[best[1]], parts[best[1] + 1]
            merged, i = [], 0
            while i < len(parts):
                if i < len(parts) - 1 and parts[i] == a and parts[i + 1] == b:
                    merged.append(a + b)
                    i += 2
                else:
                    merged.append(parts[i])
                    i += 1
            parts = merged
        self.memo[word] = parts
        return parts

    def encode(self, s):
        ids, i, start = [], 0, 0
        chunks = []
        while i < len(s):                       # added (special) tokens are cut out first, longest first
            hit = next((a for a in self.added if s.startswith(a, i)), None)
            if hit:
                chunks.append((s[start:i], False))
                chunks.append((hit, True))
                i += len(hit)
                start = i
            else:
                i += 1
        chunks.append((s[start:], False))
        for chunk, special in chunks:
            if special:
                ids.append(self.added_id[chunk])
                continue
            for piece in digits_split(chunk):
                for word in gpt2_split(piece):
                    for tok in self.bpe("".join(self.enc[b] for b in word.encode("utf-8"))):
                        ids.append(self.vocab[tok])
        return ids


def tokenizer():
    return Tokenizer(model_file("tokenizer.json"))


# ---- the float32 baseline: a plain forward pass of the same weights, with a key-value cache -----------------------
class Float32:
    def __init__(self, P, stats=None):
        self.E = P["model.embed_tokens.weight"]
        self.norm = P["model.norm.weight"]
        self.L = []
        for i in range(LAYERS):
            p = "model.layers.%d." % i
            T = lambda n: np.ascontiguousarray(P[p + n + ".weight"].T)
            self.L.append({"q": T("self_attn.q_proj"), "k": T("self_attn.k_proj"), "v": T("self_attn.v_proj"),
                           "o": T("self_attn.o_proj"), "g": T("mlp.gate_proj"), "u": T("mlp.up_proj"),
                           "d": T("mlp.down_proj"), "n1": P[p + "input_layernorm.weight"],
                           "n2": P[p + "post_attention_layernorm.weight"]})
        inv = (np.float32(1.0) / (np.float32(THETA) ** (np.arange(0, HEAD, 2, dtype=np.float32) / np.float32(HEAD))))
        self.inv_freq = inv.astype(np.float32)
        self.stats = stats

    def site(self, name, i, x):
        if self.stats is not None:
            k = (name, i)
            self.stats[k] = max(self.stats.get(k, 0.0), float(np.abs(x).max()))

    def rms(self, x, w):
        var = (x * x).mean(-1, keepdims=True)
        return (x / np.sqrt(var + np.float32(1e-5))) * w

    def rope(self, x, pos):
        f = pos[..., None].astype(np.float32) * self.inv_freq                  # [B, L, 32]
        cos = np.cos(np.concatenate([f, f], -1))[:, None]
        sin = np.sin(np.concatenate([f, f], -1))[:, None]
        rot = np.concatenate([-x[..., HEAD // 2:], x[..., :HEAD // 2]], -1)
        return x * cos + rot * sin

    def forward(self, ids, pos, cache, kvalid):
        """ids, pos: [B, L]; cache: per layer (K, V) arrays [B, KV, T, 64] or None; kvalid: [B, L, Tk] bool."""
        B, L = ids.shape
        x = self.E[ids]
        new = []
        for i, w in enumerate(self.L):
            self.site("residual", i, x)
            h = self.rms(x, w["n1"])
            self.site("attention input", i, h)
            q = (h @ w["q"]).reshape(B, L, HEADS, HEAD).transpose(0, 2, 1, 3)
            k = (h @ w["k"]).reshape(B, L, KV, HEAD).transpose(0, 2, 1, 3)
            v = (h @ w["v"]).reshape(B, L, KV, HEAD).transpose(0, 2, 1, 3)
            q, k = self.rope(q, pos), self.rope(k, pos)
            self.site("q", i, q)
            self.site("k", i, k)
            self.site("v", i, v)
            if cache is not None:
                k = np.concatenate([cache[i][0], k], 2)
                v = np.concatenate([cache[i][1], v], 2)
            new.append((k, v))
            kk = np.repeat(k, HEADS // KV, axis=1)
            vv = np.repeat(v, HEADS // KV, axis=1)
            s = (q @ kk.swapaxes(-1, -2)) / np.float32(8.0)
            s = np.where(kvalid[:, None], s, np.float32(-np.inf))
            s = np.exp(s - s.max(-1, keepdims=True))
            ctx = ((s / s.sum(-1, keepdims=True)) @ vv).transpose(0, 2, 1, 3).reshape(B, L, HIDDEN)
            self.site("o input", i, ctx)
            x = x + ctx @ w["o"]
            self.site("residual mid", i, x)
            h = self.rms(x, w["n2"])
            self.site("mlp input", i, h)
            g, u = h @ w["g"], h @ w["u"]
            self.site("gate", i, g)
            self.site("up", i, u)
            a = (g / (np.float32(1.0) + np.exp(-g))) * u
            self.site("down input", i, a)
            x = x + a @ w["d"]
        self.site("residual", LAYERS, x)
        h = self.rms(x, self.norm)
        self.site("logits input", 0, h)
        return h @ self.E.T, new


# ---- the onnxruntime baseline: the onnx-community float32 export of the same model --------------------------------
def onnx_file(name):
    o = PINS["onnx"]
    return fetch("https://huggingface.co/%s/resolve/%s/%s" % (o["repo"], o["revision"], name),
                 os.path.join(CACHE, "onnx", name), o["files"][name])


class Onnx:
    def __init__(self, threads=0):
        import onnxruntime as ort
        onnx_file("onnx/model.onnx_data")
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
            so.inter_op_num_threads = 1
        self.s = ort.InferenceSession(onnx_file("onnx/model.onnx"), so, providers=["CPUExecutionProvider"])
        self.inputs = [i.name for i in self.s.get_inputs()]
        self.outputs = [o.name for o in self.s.get_outputs()]

    def forward(self, ids, pos, cache, kvalid):
        """The model applies its own causal mask; it is given the keys each row may read (the last row of kvalid)."""
        B = ids.shape[0]
        feed = {"input_ids": ids.astype(np.int64), "attention_mask": kvalid[:, -1, :].astype(np.int64),
                "position_ids": np.ascontiguousarray(pos, dtype=np.int64)}
        for i in range(LAYERS):
            k, v = cache[i] if cache is not None else (np.zeros((B, KV, 0, HEAD), np.float32),) * 2
            feed["past_key_values.%d.key" % i] = k
            feed["past_key_values.%d.value" % i] = v
        res = dict(zip(self.outputs, self.s.run(None, {k: v for k, v in feed.items() if k in self.inputs})))
        new = [(res["present.%d.key" % i], res["present.%d.value" % i]) for i in range(LAYERS)]
        return res["logits"], new


# ---- the exact model ----------------------------------------------------------------------------------------------
A = 16                       # activations: integer x stands for x * 2^-16
WB = 16                      # weights: integer w stands for w * 2^-WB (bfloat16 values rounded once)
CLAMP = {                    # clamps in real units, per site; see bounds.py and the measured peaks
    "residual": 2 ** 16, "attention input": 2 ** 12, "q": 2 ** 7, "k": 2 ** 7, "v": 2 ** 12, "o input": 2 ** 12,
    "mlp input": 2 ** 11, "gate": 2 ** 12, "up": 2 ** 12, "down input": 2 ** 13, "logits input": 2 ** 14}
SPLIT = {"down input": 256}  # the down product's 1,536 inputs in chunks of 256: each chunk exact in float64, summed in int64
# Each clamp is the largest power of two the certificate allows (bounds.py): a product's input clamp times the largest
# row sum of its integer weights below 2^53; q and k with 64 C_q C_k below 2^53. The measured peaks and the margin
# clamp / peak are in the README; the number of clamped values is counted on every run.
EXP_STEP, EXP_N = 8, 24 * 256
SILU_STEP, SILU_LO, SILU_N = 8, 16, 32 * 256
ROPE = 20                    # cos and sin at 2^-20
ROPE_POS = 512
NORM_BITS = 26               # RMS norm: x is shifted right until max |x| < 2^26, so the sum of squares stays below 2^62


def rshift_round(v, k):
    """floor(v / 2^k + 1/2), round to nearest with halves up; k = 0 leaves v."""
    return (v + (1 << (k - 1))) >> k if k > 0 else v


def isqrt(n):
    """floor(sqrt(n)) for 0 <= n < 2^62, asserted by its bracket s^2 <= n < (s + 1)^2."""
    assert (n >= 0).all() and (n < (1 << 62)).all()
    s = np.sqrt(n.astype(np.float64)).astype(np.int64)
    for _ in range(4):
        s = np.where(s * s > n, s - 1, s)
        s = np.where((s + 1) * (s + 1) <= n, s + 1, s)
    assert ((s * s <= n) & ((s + 1) * (s + 1) > n)).all()
    return s


def fdiv(num, den):
    """floor(num / den) for den > 0, asserted by its bracket q den <= num < (q + 1) den."""
    den = np.asarray(den, dtype=np.int64)
    assert (den > 0).all()
    q = num // den
    assert ((q * den <= num) & (num < (q + 1) * den)).all()
    return q


def load_table(name, shape=None):
    with open(os.path.join(HERE, "tables", name)) as f:
        t = np.array([int(line) for line in f if not line.startswith("#")], dtype=np.int64)
    return t.reshape(shape) if shape else t


def int_weights(wb=None):
    """The integer weights: round(w * 2^WB) of each bfloat16 value, ties to even (exact arithmetic plus one rounding;
    most values need no rounding). Computed once from model.safetensors and kept as int32 .npy files in the cache,
    transposed to [in, out]; opened memory-mapped."""
    wb = WB if wb is None else wb
    d = os.path.join(CACHE, "int32-wb%d" % wb)
    done = os.path.join(d, "DONE")
    if not os.path.exists(done):
        os.makedirs(d, exist_ok=True)
        for name, a in iter_safetensors(model_file("model.safetensors")):
            if a.ndim == 2:
                a = a.T if name != "model.embed_tokens.weight" else a          # [in, out]; the embedding stays [V, 576]
                out = np.empty(a.shape, dtype=np.int32)
                for s in range(0, a.shape[0], 4096):
                    v = np.rint(a[s:s + 4096].astype(np.float64) * 2.0 ** wb)
                    assert np.abs(v).max() < 2 ** 31
                    out[s:s + 4096] = v.astype(np.int32)
            else:
                out = np.rint(a.astype(np.float64) * 2.0 ** A).astype(np.int64)  # norm weights at 2^-16
            np.save(os.path.join(d, name + ".npy"), np.ascontiguousarray(out))
        open(done, "w").write("from %s\n" % PINS["model"]["files"]["model.safetensors"])
    return {f[:-4]: np.load(os.path.join(d, f), mmap_mode="r") for f in os.listdir(d) if f.endswith(".npy")}


class Exact:
    def __init__(self, W=None, keep_f64=True):
        self.W = W if W is not None else int_weights()
        self.E = self.W["model.embed_tokens.weight"]                          # [V, 576] at 2^-WB
        self.Et = load_table("exp.txt")
        self.St = load_table("silu.txt")
        self.cos = load_table("cos.txt", (ROPE_POS, HEAD // 2))
        self.sin = load_table("sin.txt", (ROPE_POS, HEAD // 2))
        self.C = {k: v << A for k, v in CLAMP.items()}
        self.clamped, self.peak, self.layer_peak = {}, {}, {}
        self.keep = keep_f64
        self.f64 = {}
        self.eps = [int(round(EPS * 2 ** (2 * A - 2 * s))) for s in range(A + 1)]   # eps at 2^-(32 - 2s)

    def clamp(self, x, site, layer=None):
        c = self.C[site]
        a = np.abs(x)
        n = int((a > c).sum())
        if n:
            self.clamped[site] = self.clamped.get(site, 0) + n
        top = int(a.max()) if a.size else 0
        self.peak[site] = max(self.peak.get(site, 0), top)
        if layer is not None:
            self.layer_peak[(site, layer)] = max(self.layer_peak.get((site, layer), 0), top)
        return np.clip(x, -c, c)

    def matrix(self, name):
        """A weight matrix as float64 [in, out], converted from int32 (exactly). Kept for the run when keep_f64,
        else converted at each use, one matrix at a time."""
        w = self.f64.get(name)
        if w is None:
            w = np.asarray(self.W[name], dtype=np.float64)
            if self.keep:
                self.f64[name] = w
        return w

    def linear(self, x, name, site):
        xc = self.clamp(x, site).astype(np.float64)
        w = self.matrix(name)
        n = SPLIT.get(site, w.shape[0])
        y = sum((xc[:, s:s + n] @ w[s:s + n]).astype(np.int64) for s in range(0, w.shape[0], n))  # exact: bounds.py
        return rshift_round(y, WB)

    def rms(self, x, wname):
        """RMS normalisation of each token (last axis, 576 values), x and result at 2^-16."""
        top = np.abs(x).max(-1, keepdims=True)
        sh = np.maximum(0, np.frexp(top.astype(np.float64))[1] - NORM_BITS).astype(np.int64)  # bit length - 26
        xs = x >> sh
        ss = (xs * xs).sum(-1, keepdims=True)                                 # at 2^-(32 - 2 sh), below 2^62
        ms = fdiv(ss, HIDDEN)
        assert (sh <= A).all()
        eps = np.array(self.eps, dtype=np.int64)[sh]
        r = isqrt(ms + np.maximum(eps, 1))                                    # sqrt(mean x^2 + eps) at 2^-(16 - sh)
        y = fdiv(x << (A - sh), r)                                            # x / r at 2^-16
        assert (np.abs(y) <= 25 << A).all()                                   # |x_i| <= sqrt(576) rms: bounds.py
        return rshift_round(y * np.asarray(self.W[wname]), A)

    def rope(self, x, pos):
        c = self.cos[pos][:, None]                                            # [B, 1, L, 32] at 2^-20
        s = self.sin[pos][:, None]
        x1, x2 = x[..., :HEAD // 2], x[..., HEAD // 2:]
        return np.concatenate([rshift_round(x1 * c - x2 * s, ROPE), rshift_round(x2 * c + x1 * s, ROPE)], -1)

    def exp(self, t):
        k = np.minimum(t >> EXP_STEP, EXP_N)
        r = t & ((1 << EXP_STEP) - 1)
        return (self.Et[k] * ((1 << EXP_STEP) - r) + self.Et[np.minimum(k + 1, EXP_N)] * r) >> EXP_STEP

    def silu(self, x):
        top = SILU_N << SILU_STEP
        u = x + (SILU_LO << A)
        uc = np.clip(u, 0, top - 1)
        k, r = uc >> SILU_STEP, uc & ((1 << SILU_STEP) - 1)
        g = (self.St[k] * ((1 << SILU_STEP) - r) + self.St[k + 1] * r) >> SILU_STEP
        return np.where((u >= 0) & (u < top), g, np.where(u < 0, 0, x))

    def attention(self, q, k, v, kvalid):
        """q [B, 9, L, 64]; k, v [B, 3, T, 64]; head h reads key-value head h // 3. Scores at 2^-32; the scale
        1/sqrt(64) = 2^-3 is the 3 in the shift by 19."""
        B, _, L, _ = q.shape
        qc = self.clamp(q, "q").astype(np.float64).reshape(B, KV, HEADS // KV, L, HEAD)
        kc = self.clamp(k, "k").astype(np.float64)[:, :, None]
        vc = self.clamp(v, "v").astype(np.float64)[:, :, None]
        s = (qc @ kc.swapaxes(-1, -2)).astype(np.int64)                     # [B, 3, 3, L, T]
        key = kvalid[:, None, None]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - s, 0) >> (A + 3)
        e = np.where(key, self.exp(t), 0)
        p = fdiv(e << A, e.sum(-1, keepdims=True))
        ctx = (p.astype(np.float64) @ vc).astype(np.int64)                   # at 2^-32
        return rshift_round(ctx, A).reshape(B, HEADS, L, HEAD)

    def forward(self, ids, pos, cache, kvalid):
        B, L = ids.shape
        x = rshift_round(np.asarray(self.E[ids], dtype=np.int64), WB - A)
        new = []
        for i in range(LAYERS):
            p = "model.layers.%d." % i
            x = self.clamp(x, "residual", i)
            h = self.rms(x, p + "input_layernorm.weight").reshape(B * L, HIDDEN)
            q = self.linear(h, p + "self_attn.q_proj.weight", "attention input").reshape(B, L, HEADS, HEAD)
            k = self.linear(h, p + "self_attn.k_proj.weight", "attention input").reshape(B, L, KV, HEAD)
            v = self.linear(h, p + "self_attn.v_proj.weight", "attention input").reshape(B, L, KV, HEAD)
            q = self.rope(q.transpose(0, 2, 1, 3), pos)
            k = self.rope(k.transpose(0, 2, 1, 3), pos)
            v = v.transpose(0, 2, 1, 3)
            if cache is not None:
                k = np.concatenate([cache[i][0], k], 2)
                v = np.concatenate([cache[i][1], v], 2)
            new.append((k, v))
            ctx = self.attention(q, k, v, kvalid).transpose(0, 2, 1, 3).reshape(B * L, HIDDEN)
            x = x + self.linear(ctx, p + "self_attn.o_proj.weight", "o input").reshape(B, L, HIDDEN)
            x = self.clamp(x, "residual", i)
            h = self.rms(x, p + "post_attention_layernorm.weight").reshape(B * L, HIDDEN)
            g = self.clamp(self.linear(h, p + "mlp.gate_proj.weight", "mlp input"), "gate")
            u = self.clamp(self.linear(h, p + "mlp.up_proj.weight", "mlp input"), "up")
            a = rshift_round(self.silu(g) * u, A)
            x = x + self.linear(a, p + "mlp.down_proj.weight", "down input").reshape(B, L, HIDDEN)
        x = self.clamp(x, "residual", LAYERS)
        h = self.rms(x, "model.norm.weight").reshape(B * L, HIDDEN)
        return self.logits(h).reshape(B, L, VOCAB), new

    def logits(self, h):
        """h @ E^T at 2^-16, the embedding converted in blocks of 8,192 rows."""
        hc = self.clamp(h, "logits input").astype(np.float64)
        out = np.empty((h.shape[0], VOCAB), dtype=np.int32)
        for s in range(0, VOCAB, 8192):
            e = np.asarray(self.E[s:s + 8192], dtype=np.float64)
            blk = rshift_round((hc @ e.T).astype(np.int64), WB)
            assert np.abs(blk).max() < (1 << 31)
            out[:, s:s + 8192] = blk
        return out


# ---- drivers ------------------------------------------------------------------------------------------------------
def run_prompts(model, tok, texts, batch, on_logits=None, gen=GEN):
    """Prefill each batch (right-padded), hand the logits of every prompt position to on_logits(row, logits), then
    continue greedily for `gen` tokens with the key-value cache. A row attends only to its own prompt and its own
    generated tokens; padded keys are masked. Returns the continuations, one list of ids per prompt."""
    out = []
    for s in range(0, len(texts), batch):
        enc = [tok.encode(t) for t in texts[s:s + batch]]
        B, Lmax = len(enc), max(len(e) for e in enc)
        lens = np.array([len(e) for e in enc])
        ids = np.zeros((B, Lmax), dtype=np.int64)
        for b, e in enumerate(enc):
            ids[b, :len(e)] = e
        pos = np.broadcast_to(np.arange(Lmax), (B, Lmax))
        idx = np.arange(Lmax)
        kvalid = (idx[None, None, :] <= idx[None, :, None]) & (idx[None, None, :] < lens[:, None, None])
        logits, cache = model.forward(ids, pos, None, kvalid)
        for b in range(B):
            if on_logits is not None:
                on_logits(s + b, logits[b, :lens[b]])
        nxt = np.array([int(np.argmax(logits[b, lens[b] - 1])) for b in range(B)])
        cont = [[int(t)] for t in nxt]
        for t in range(gen - 1):
            T = Lmax + t + 1
            idx = np.arange(T)
            kv = (idx[None] < lens[:, None]) | ((idx[None] >= Lmax) & (idx[None] <= Lmax + t))
            logits, cache = model.forward(nxt[:, None], (lens + t)[:, None], cache, kv[:, None, :])
            nxt = np.array([int(np.argmax(logits[b, 0])) for b in range(B)])
            for b in range(B):
                cont[b].append(int(nxt[b]))
        out += cont
    return out


def text_windows(tok, n=16, size=512):
    ids = tok.encode(text())[: n * size]
    assert len(ids) == n * size
    return [np.array(ids[i * size:(i + 1) * size], dtype=np.int64)[None] for i in range(n)]


def run_window(model, ids):
    L = ids.shape[1]
    pos = np.arange(L)[None]
    kvalid = np.tril(np.ones((L, L), dtype=bool))[None]
    logits, _ = model.forward(ids, pos, None, kvalid)
    return logits[0]


# ---- hashes, the text, the command line ---------------------------------------------------------------------------
def engine(name, threads=0):
    if name == "exact":
        return Exact()
    if name == "float32":
        return Float32(read_safetensors(model_file("model.safetensors")))
    if name == "onnx":
        return Onnx(threads)
    raise SystemExit("unknown engine " + name)


def as_bytes(logits):
    """Exact logits as little-endian int32 (scale 2^-16); float logits as little-endian float32."""
    return np.ascontiguousarray(logits).astype("<i4" if logits.dtype == np.int32 else "<f4").tobytes()


def prompt_run(eng, batch, keep=False):
    """The 64 prompts: SHA-256 over the logits of every prompt position (prompt by prompt, position by position,
    49,152 values each) and SHA-256 over the 64 continuations of 48 token ids (int32, little-endian)."""
    h = hashlib.sha256()
    kept = []

    def on_logits(row, lg):
        h.update(as_bytes(lg))
        if keep:
            kept.append(np.array(lg))
    cont = run_prompts(eng, tokenizer(), prompts(), batch, on_logits)
    hc = hashlib.sha256(np.array(cont, dtype="<i4").tobytes()).hexdigest()
    return h.hexdigest(), hc, cont, kept


def text_run(eng):
    """The 16 windows of 512 tokens: negative log-likelihood of each next token (in float64 from the logits; exact
    logits are divided by 2^16 first) and the top-1 token at each of the 8,176 predicted positions."""
    nll, top = [], []
    for w in text_windows(tokenizer()):
        lg = run_window(eng, w)
        top.append(np.argmax(lg[:-1], -1))
        scale = 2.0 ** A if lg.dtype == np.int32 else 1.0
        for s in range(0, lg.shape[0] - 1, 128):                    # rows s .. predict tokens s+1 .., in blocks
            e = min(s + 128, lg.shape[0] - 1)
            z = lg[s:e].astype(np.float64) / scale
            mx = z.max(-1, keepdims=True)
            lse = np.log(np.exp(z - mx).sum(-1)) + mx[:, 0]
            nll.append(lse - z[np.arange(e - s), w[0, s + 1:e + 1]])
    return np.concatenate(nll), np.concatenate(top)


def expected():
    lines = open(os.path.join(HERE, "expected.sha256")).read().split("\n")
    return lines[0].split()[0], lines[1].split()[0]


def main(argv):
    arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    if len(argv) > 1 and argv[1] == "hash":
        name, batch, threads = arg("--engine", "exact"), int(arg("--batch", "8")), int(arg("--threads", "0"))
        save = arg("--save", None)
        eng = Exact(keep_f64=False) if name == "exact" and "--lean" in argv else engine(name, threads)
        hl, hc, cont, kept = prompt_run(eng, batch, keep=save is not None)
        print("%s %s %s batch=%d" % (hl, hc, name, batch))
        if save:
            np.save(save + ".logits.npy", np.concatenate(kept))
            np.save(save + ".cont.npy", np.array(cont, dtype=np.int32))
        if name == "exact":
            print("clamped", sum(eng.clamped.values()), eng.clamped)
            print("peaks (real) and clamps:", "; ".join("%s %.3f / %d" % (k, v / 2.0 ** A, CLAMP[k])
                                                        for k, v in sorted(eng.peak.items())))
        return 0
    if len(argv) > 1 and argv[1] == "text":
        name, save = arg("--engine", "exact"), arg("--save", None)
        nll, top = text_run(engine(name))
        print("%s perplexity %.6f over %d tokens" % (name, math.exp(nll.mean()), nll.size))
        if save:
            np.save(save + ".nll.npy", nll)
            np.save(save + ".top.npy", top)
        return 0
    if len(argv) > 1 and argv[1] == "check":
        ex = Exact()
        hl, hc, cont_e, lg_e = prompt_run(ex, 8, keep=True)
        el, ec = expected()
        ok = hl == el and hc == ec
        print("exact    logits %s  continuations %s  %s" % (hl, hc, "MATCH" if ok else "DIFFERENT"))
        print("         clamped values: %d" % sum(ex.clamped.values()))
        del ex
        f = Float32(read_safetensors(model_file("model.safetensors")))
        fl, fc, cont_f, lg_f = prompt_run(f, 8, keep=True)
        print("float32  logits %s  continuations %s" % (fl, fc))
        del f
        e = np.concatenate(lg_e).astype(np.float64) / 2.0 ** A
        g = np.concatenate(lg_f).astype(np.float64)
        print("exact against float32 over %d prompt positions: top-1 agreement %d, largest |logit difference| %.5f, "
              "mean %.6f; continuations equal %d of %d" % (
                  e.shape[0], int((e.argmax(-1) == g.argmax(-1)).sum()), np.abs(e - g).max(), np.abs(e - g).mean(),
                  sum(a == b for a, b in zip(cont_e, cont_f)), len(cont_e)))
        try:
            o = Onnx()
        except ImportError:
            print("onnx     onnxruntime is not installed here")
        else:
            ol, oc, _, _ = prompt_run(o, 8)
            print("onnx     logits %s  continuations %s" % (ol, oc))
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
