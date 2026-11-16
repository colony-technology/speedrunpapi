"""Exact inference for a language model: HuggingFaceTB/SmolLM2-135M (and -360M, -1.7B) in integer arithmetic.

The method of proofs/exact-embeddings on a decoder. Every tensor is an integer array with a power-of-two scale;
element-wise work is NumPy int64; the only floating-point operation is matrix multiplication by the machine's
float64 BLAS on integer-valued arrays whose partial sums stay below 2^53 (bounds.py). exp, SiLU and the rotary cos
and sin are integer tables (tables/, make_tables.py). The output is the next-token logits at every position, as
integers at scale 2^-16, and greedy continuations computed from them.

The same file holds the pinned downloads, a byte-level BPE tokenizer in plain Python, a plain float32 forward pass
of the same weights (the baseline), an onnxruntime baseline on the onnx-community export, and the evaluation.

The model is a block of pins.json, chosen by --model (or the environment variable EXACT_LLM_MODEL); its sizes come
from its pinned config.json. SmolLM2-135M is the default and runs every engine; the larger two run exact-16, the
float32 baseline and onnxruntime where an export is pinned.

usage:
  python exact_llm.py check [--model M] [--routes f64,f32,i8,t3] [--no-float] [--no-onnx] [--peaks FILE]
                                                  digests, the hashes against expected*.sha256, baselines, distance
  python exact_llm.py hash --engine exact|exact16-f64|exact16-f32|exact16-i8|exact16-t3|float32|onnx [--batch N]
                           [--threads N]
                           [--model M]
"""
import gzip
import hashlib
import json
import math
import os
import struct
import sys
import time
import unicodedata
import urllib.request
from fractions import Fraction

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = json.load(open(os.path.join(HERE, "pins.json")))
CACHE = os.environ.get("EXACT_LLM_CACHE", os.path.join(HERE, ".cache"))
MODELS = tuple(PINS["models"])                  # the first is the default
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
    return fetch("https://huggingface.co/%s/resolve/%s/%s" % (PIN["repo"], PIN["revision"], name),
                 os.path.join(MCACHE, "model", name), PIN["files"][name])


def use_model(name):
    """Select a model of pins.json and take its sizes from its pinned config.json. The default model's files stay at
    the top of the cache; another model's go in a folder of its own name. Asserts what the code assumes: a Llama
    decoder with SiLU, tied embedding, no biases, rotary positions on halves of 64-wide heads, no rope scaling."""
    global MODEL, PIN, MCACHE, LAYERS, HIDDEN, HEADS, KV, HEAD, FF, VOCAB, THETA, EPS, NORM_BITS, RMS_Y, SUFFIX
    if name not in PINS["models"]:
        raise SystemExit("unknown model %s; pins.json has %s" % (name, ", ".join(MODELS)))
    MODEL, PIN = name, PINS["models"][name]
    MCACHE = CACHE if name == MODELS[0] else os.path.join(CACHE, name)
    SUFFIX = "" if name == MODELS[0] else "-" + name                # expected-16<SUFFIX>.sha256, bounds-16<SUFFIX>.json
    c = json.load(open(model_file("config.json"), encoding="utf-8"))
    LAYERS, HIDDEN = c["num_hidden_layers"], c["hidden_size"]
    HEADS, KV = c["num_attention_heads"], c["num_key_value_heads"]
    HEAD = c.get("head_dim") or HIDDEN // HEADS
    FF, VOCAB, THETA = c["intermediate_size"], c["vocab_size"], c["rope_theta"]
    EPS = Fraction(repr(c["rms_norm_eps"]))                          # 1e-05 as the decimal it is written as
    assert c["model_type"] == "llama" and c["hidden_act"] == "silu" and c["tie_word_embeddings"], name
    assert not c.get("attention_bias") and not c.get("mlp_bias") and not c.get("rope_scaling"), name
    assert not c.get("rope_interleaved", False) and HEAD == 64 and HEADS * HEAD == HIDDEN and HEADS % KV == 0, name
    # RMS norm: x is shifted right until max |x| < 2^NORM_BITS, so the sum of HIDDEN squares stays below 2^62
    NORM_BITS = (62 - (HIDDEN - 1).bit_length()) // 2
    # every normalised value is at most sqrt(HIDDEN) times the root mean square; with the floors of the integer
    # mean, square root and eps, at most sqrt(HIDDEN) (1 + 1/128): RMS_Y is the least integer at or above that
    RMS_Y = math.isqrt(HIDDEN * 129 * 129 // (128 * 128))
    while (128 * RMS_Y) ** 2 < HIDDEN * 129 * 129:
        RMS_Y += 1


use_model(os.environ.get("EXACT_LLM_MODEL", MODELS[0]))


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
def iter_safetensors(path, names=None, raw=False):
    """Yield (name, float32 array) one tensor at a time, reading only that tensor's bytes. names: a collection of
    names, or a function of (name, shape) that says which tensors to read. raw: the bfloat16 bits as uint16."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n).decode("utf-8"))
        header.pop("__metadata__", None)
        for name, t in header.items():
            if names is not None and not (names(name, t["shape"]) if callable(names) else name in names):
                continue
            assert t["dtype"] == "BF16", (name, t["dtype"])
            b, e = t["data_offsets"]
            f.seek(8 + n + b)
            bits = np.frombuffer(f.read(e - b), dtype="<u2").reshape(t["shape"])
            yield name, bits if raw else widen(bits)


def widen(bits):
    """bfloat16 bits (uint16) to float32, exactly: the 16 bits become the high half."""
    return (bits.astype(np.uint32) << 16).view(np.float32)


def read_safetensors(path, names=None, raw=False):
    return dict(iter_safetensors(path, names, raw))


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
def n_params():
    """Weights of the model, from its config: embedding (tied), per layer q, k, v, o, gate, up, down and two norms."""
    attn = HIDDEN * (2 * HIDDEN + 2 * KV * HEAD)
    return VOCAB * HIDDEN + LAYERS * (attn + 3 * HIDDEN * FF + 2 * HIDDEN) + HIDDEN


LEAN_F32_BYTES = 1 << 32     # float32 weights above 4 GB are kept as bfloat16 and widened one matrix at a time


class _Layer(dict):
    """One layer's float32 weights; a matrix kept as bfloat16 bits is widened to float32 [in, out] at each read."""
    def __getitem__(self, k):
        v = dict.__getitem__(self, k)
        return np.ascontiguousarray(widen(v).T) if v.dtype == np.uint16 else v


class Float32:
    def __init__(self, P=None, stats=None, lean=None):
        """P: the weights as float32, or None to read them here. lean: keep the matrices as bfloat16 bits and widen
        each at its use, giving BLAS the same float32 arrays (so the same results) in half the memory; by default
        when the float32 weights would exceed LEAN_F32_BYTES."""
        if P is None:
            self.lean = 4 * n_params() > LEAN_F32_BYTES if lean is None else lean
            P = read_safetensors(model_file("model.safetensors"), raw=self.lean)
        else:
            self.lean = False
        f32 = lambda a: widen(a) if a.dtype == np.uint16 else a
        self.E = f32(P["model.embed_tokens.weight"])
        self.norm = f32(P["model.norm.weight"])
        self.L = []
        for i in range(LAYERS):
            p = "model.layers.%d." % i
            T = lambda n: P[p + n + ".weight"] if self.lean else np.ascontiguousarray(P[p + n + ".weight"].T)
            self.L.append(_Layer({"q": T("self_attn.q_proj"), "k": T("self_attn.k_proj"),
                                  "v": T("self_attn.v_proj"), "o": T("self_attn.o_proj"), "g": T("mlp.gate_proj"),
                                  "u": T("mlp.up_proj"), "d": T("mlp.down_proj"),
                                  "n1": f32(P[p + "input_layernorm.weight"]),
                                  "n2": f32(P[p + "post_attention_layernorm.weight"])}))
        del P
        inv = (np.float32(1.0) / (np.float32(THETA) ** (np.arange(0, HEAD, 2, dtype=np.float32) / np.float32(HEAD))))
        self.inv_freq = inv.astype(np.float32)
        self.stats = stats

    def site(self, name, i, x):
        if self.stats is not None:
            k = (name, i)
            self.stats[k] = max(self.stats.get(k, 0.0), float(np.abs(x).max()))

    def rms(self, x, w):
        var = (x * x).mean(-1, keepdims=True)
        return (x / np.sqrt(var + np.float32(float(EPS)))) * w

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
    o = PIN["onnx"]
    return fetch("https://huggingface.co/%s/resolve/%s/%s" % (o["repo"], o["revision"], name),
                 os.path.join(MCACHE, "onnx", name), o["files"][name])


class Onnx:
    def __init__(self, threads=0):
        import onnxruntime as ort
        if PIN["onnx"] is None:
            raise LookupError(PIN.get("onnx_note", "no onnx export pinned for " + MODEL))
        for name in PIN["onnx"]["files"]:                                    # the graph and its external data, if any
            onnx_file(name)
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
# NORM_BITS and RMS_Y come from the width, in use_model: 26 and 25 at 576 (135M), 26 and 32 at 960, 25 and 46 at 2,048


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


def int_weights(wb=None, small=False):
    """The integer weights: round(w * 2^WB) of each bfloat16 value, ties to even (exact arithmetic plus one rounding;
    most values need no rounding). Computed once from model.safetensors and kept as int32 .npy files in the cache,
    transposed to [in, out]; opened memory-mapped. small: only the embedding and the norm weights, which is all
    exact-16 reads at this scale (its products use int16_weights)."""
    wb = WB if wb is None else wb
    d = os.path.join(MCACHE, "int32-wb%d%s" % (wb, "-small" if small else ""))
    done = os.path.join(d, "DONE")
    want = (lambda name, shape: len(shape) == 1 or name == "model.embed_tokens.weight") if small else None
    if not os.path.exists(done):
        os.makedirs(d, exist_ok=True)
        for name, a in iter_safetensors(model_file("model.safetensors"), want):
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
        open(done, "w").write("from %s\n" % PIN["files"]["model.safetensors"])
    return {f[:-4]: np.load(os.path.join(d, f), mmap_mode="r") for f in os.listdir(d) if f.endswith(".npy")}


def rope_table_names():
    """cos and sin tables of the model's rotary base (make_tables.py): the 135M's 100,000 keeps its first names."""
    return ("cos.txt", "sin.txt") if THETA == 100000 else ("cos-%d.txt" % THETA, "sin-%d.txt" % THETA)


class Exact:
    def __init__(self, W=None, keep_f64=False, clamps=None):
        self.W = W if W is not None else int_weights()
        self.E = self.W["model.embed_tokens.weight"]                          # [V, HIDDEN] at 2^-WB
        self.Et = load_table("exp.txt")
        self.St = load_table("silu.txt")
        cname, sname = rope_table_names()
        self.cos = load_table(cname, (ROPE_POS, HEAD // 2))
        self.sin = load_table(sname, (ROPE_POS, HEAD // 2))
        self.clamps = CLAMP if clamps is None else clamps                    # real units, per site
        self.C = {k: v << A for k, v in self.clamps.items()}
        self.clamped, self.peak, self.layer_peak = {}, {}, {}
        self.keep = keep_f64
        self.f64 = {}
        self.eps = [int(round(EPS * 2 ** (2 * A - 2 * s))) for s in range(A + 1)]   # eps at 2^-(32 - 2s)

    def mul(self, a, b, kind="element-wise"):
        """The element-wise integer product a * b (int64): NumPy's here; the t3 route's by adds."""
        return a * b

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

    def prepare(self, x, site):
        """A product input as every product that reads it needs it, made once: clamped at its site."""
        return self.clamp(x, site)

    def linear(self, x, name, site):
        """x as prepare() made it for this site."""
        xc = x.astype(np.float64)
        w = self.matrix(name)
        n = SPLIT.get(site, w.shape[0])
        y = sum((xc[:, s:s + n] @ w[s:s + n]).astype(np.int64) for s in range(0, w.shape[0], n))  # exact: bounds.py
        return rshift_round(y, WB)

    def rms(self, x, wname):
        """RMS normalisation of each token (last axis, HIDDEN values), x and result at 2^-16."""
        top = np.abs(x).max(-1, keepdims=True)
        sh = np.maximum(0, np.frexp(top.astype(np.float64))[1] - NORM_BITS).astype(np.int64)  # bit length - NORM_BITS
        xs = x >> sh
        ss = self.mul(xs, xs).sum(-1, keepdims=True)                               # at 2^-(32 - 2 sh), below 2^62
        ms = fdiv(ss, HIDDEN)
        assert (sh <= A).all()
        eps = np.array(self.eps, dtype=np.int64)[sh]
        r = isqrt(ms + np.maximum(eps, 1))                                    # sqrt(mean x^2 + eps) at 2^-(16 - sh)
        y = fdiv(x << (A - sh), r)                                            # x / r at 2^-16
        assert (np.abs(y) <= RMS_Y << A).all()                                # |x_i| <= sqrt(HIDDEN) rms: bounds.py
        return rshift_round(self.mul(y, np.asarray(self.W[wname])), A)

    def rope_tables(self, pos):
        """cos and sin of each position, read once per forward pass: [B, 1, L, 32] at 2^-20."""
        return self.cos[pos][:, None], self.sin[pos][:, None]

    def rope(self, x, cs):
        c, s = cs
        x1, x2 = x[..., :HEAD // 2], x[..., HEAD // 2:]
        m = self.mul
        return np.concatenate([rshift_round(m(x1, c) - m(x2, s), ROPE), rshift_round(m(x2, c) + m(x1, s), ROPE)], -1)

    def exp(self, t):
        k = np.minimum(t >> EXP_STEP, EXP_N)
        r = t & ((1 << EXP_STEP) - 1)
        return (self.mul(self.Et[k], (1 << EXP_STEP) - r) + self.mul(self.Et[np.minimum(k + 1, EXP_N)], r)) >> EXP_STEP

    def silu(self, x):
        top = SILU_N << SILU_STEP
        u = x + (SILU_LO << A)
        uc = np.clip(u, 0, top - 1)
        k, r = uc >> SILU_STEP, uc & ((1 << SILU_STEP) - 1)
        g = (self.mul(self.St[k], (1 << SILU_STEP) - r) + self.mul(self.St[k + 1], r)) >> SILU_STEP
        return np.where((u >= 0) & (u < top), g, np.where(u < 0, 0, x))

    def cache_entry(self, k, v):
        """What the key-value cache keeps for each new position: k and v clamped. Done once per position; the
        cache is read at every later step."""
        return self.clamp(k, "k"), self.clamp(v, "v")

    def attention(self, q, k, v, kvalid):
        """q [B, 9, L, 64]; k, v [B, 3, T, 64], clamped (cache_entry); head h reads key-value head h // 3. Scores at
        2^-32; the scale 1/sqrt(64) = 2^-3 is the 3 in the shift by 19."""
        B, _, L, _ = q.shape
        qc = self.clamp(q, "q").astype(np.float64).reshape(B, KV, HEADS // KV, L, HEAD)
        kc = k.astype(np.float64)[:, :, None]
        vc = v.astype(np.float64)[:, :, None]
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
        cs = self.rope_tables(pos)
        new = []
        for i in range(LAYERS):
            p = "model.layers.%d." % i
            x = self.clamp(x, "residual", i)
            h = self.prepare(self.rms(x, p + "input_layernorm.weight").reshape(B * L, HIDDEN), "attention input")
            q = self.linear(h, p + "self_attn.q_proj.weight", "attention input").reshape(B, L, HEADS, HEAD)
            k = self.linear(h, p + "self_attn.k_proj.weight", "attention input").reshape(B, L, KV, HEAD)
            v = self.linear(h, p + "self_attn.v_proj.weight", "attention input").reshape(B, L, KV, HEAD)
            q = self.rope(q.transpose(0, 2, 1, 3), cs)
            k = self.rope(k.transpose(0, 2, 1, 3), cs)
            kv = self.cache_entry(k, v.transpose(0, 2, 1, 3))                 # each array [B, KV, L, ...]
            if cache is not None:
                kv = tuple(np.concatenate([c, e], 2) for c, e in zip(cache[i], kv))
            new.append(kv)
            ctx = self.attention(q, *kv, kvalid).transpose(0, 2, 1, 3).reshape(B * L, HIDDEN)
            ctx = self.prepare(ctx, "o input")
            x = x + self.linear(ctx, p + "self_attn.o_proj.weight", "o input").reshape(B, L, HIDDEN)
            x = self.clamp(x, "residual", i)
            h = self.prepare(self.rms(x, p + "post_attention_layernorm.weight").reshape(B * L, HIDDEN), "mlp input")
            g = self.clamp(self.linear(h, p + "mlp.gate_proj.weight", "mlp input"), "gate")
            u = self.clamp(self.linear(h, p + "mlp.up_proj.weight", "mlp input"), "up")
            a = self.prepare(rshift_round(self.mul(self.silu(g), u), A), "down input")
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


# ---- exact-16: every product a 16-bit by 16-bit integer product -------------------------------------------------
# Every product operand is a signed 16-bit integer with its own power-of-two scale; everything between products is
# Exact's. Product inputs: one shift per token vector (block16). Weights: one scale 2^g per output row, from the
# bfloat16 values (int16_weights). q, k: one shift per head vector. v: whole, as two 16-bit halves 2^15 vh + vl
# (two products, no shift, so nothing depends on other keys or later positions). p: at 2^-15, at most 2^15 - 1.
# The PEEL16 largest |x| of each product input are kept whole and multiply the same 16-bit weights; each output is
# rounded once. The integer products are exact on three routes (mm16), and the routes give the same bits.
B16 = 16
LIM16 = (1 << (B16 - 1)) - 1      # 32,767
PEEL16 = 2
CHUNK32 = 1024                    # f32 route: inputs per chunk, 1,024 x 2^14 = 2^24
N_I8 = 33025                      # i8 route: n 255^2 < 2^31 for n <= 33,025
ROUTES = ("f64", "f32", "i8")     # check's default
ROUTES_T3 = ("t3",)               # by adds and subtracts (t3.c), where a C compiler is installed: --routes t3
TOP16 = 15                        # t3: highest signed-digit position of a 16-bit value; 16 STEP words per output row


def shift_round(v, k):
    """round(v 2^-k), halves up, for integers k >= 0 (an array broadcast against v); k = 0 leaves v."""
    k = np.asarray(k, dtype=np.int64)
    assert (k >= 0).all()
    return (v + (np.left_shift(1, k) >> 1)) >> k


def bitlen(a):
    """Bit length of each integer 0 <= a < 2^53 (frexp is exact there)."""
    return np.frexp(a.astype(np.float64))[1].astype(np.int64)


def block16(x):
    """x int64 -> (x16, sh, n): x16 = round(x 2^-sh) with |x16| <= 2^15 - 1, sh >= 0 the least shift that fits, one
    shift per vector along the last axis; n counts the vectors whose rounding needed one more shift. Only those n
    vectors are rounded a second time."""
    top = np.abs(x).max(axis=-1, keepdims=True)
    sh = np.maximum(0, bitlen(top) - (B16 - 1))
    xb = shift_round(x, sh)
    over = (np.abs(xb) > LIM16).any(axis=-1, keepdims=True)
    n = int(over.sum())
    if n:
        sel = over[..., 0]
        sh = sh + over
        xb[sel] = shift_round(x[sel], sh[sel])
    assert (np.abs(xb) <= LIM16).all()
    return xb, sh, n


def int16_weights():
    """Each weight matrix as int16 [in, out] = round(w 2^g), g per output row the largest with every entry inside
    +-(2^15 - 1) (the embedding as [576, V], one g per token), from the bfloat16 values: the scaling is a power of
    two, so it is exact in float32 and the one rounding is rint's (ties to even). Kept as .npy files in the cache."""
    d = os.path.join(MCACHE, "int16-rows")
    if not os.path.exists(os.path.join(d, "DONE")):
        os.makedirs(d, exist_ok=True)
        for name, a in iter_safetensors(model_file("model.safetensors")):
            if a.ndim != 2:
                continue
            top = np.abs(a).max(1).astype(np.float64)                         # a: [out, in]
            g = (B16 - 1) - np.frexp(top)[1]
            g = np.where(top * np.exp2(g) > LIM16, g - 1, g)
            wq = np.rint(a * np.exp2(g).astype(np.float32)[:, None])
            assert np.abs(wq).max() <= LIM16
            np.save(os.path.join(d, name + ".npy"), np.ascontiguousarray(wq.T.astype(np.int16)))
            np.save(os.path.join(d, name + ".g.npy"), g.astype(np.int64))
        open(os.path.join(d, "DONE"), "w").write("from %s\n" % PIN["files"]["model.safetensors"])
    return {f[:-4]: np.load(os.path.join(d, f), mmap_mode="r") for f in os.listdir(d) if f.endswith(".npy")}


def _pb(num, payload):
    """One length-delimited protobuf field."""
    def varint(n):
        out = bytearray()
        while True:
            out.append((n & 0x7F) | (0x80 if n >> 7 else 0))
            n >>= 7
            if not n:
                return bytes(out)
    return varint(num << 3 | 2) + varint(len(payload)) + payload if isinstance(payload, bytes) else \
        varint(num << 3) + varint(payload)


def _mmi_model(ta, tb):
    """ONNX model bytes: Y (int32) = MatMulInteger(A, B), element types ta, tb (2 uint8, 3 int8), opset 13."""
    vi = lambda name, t: _pb(1, name) + _pb(2, _pb(1, _pb(1, t)))           # ValueInfo: name, tensor type, any shape
    node = _pb(1, b"A") + _pb(1, b"B") + _pb(2, b"Y") + _pb(3, b"m") + _pb(4, b"MatMulInteger")
    graph = _pb(1, node) + _pb(2, b"g") + _pb(11, vi(b"A", ta)) + _pb(11, vi(b"B", tb)) + _pb(12, vi(b"Y", 6))
    return _pb(1, 8) + _pb(8, _pb(1, b"") + _pb(2, 13)) + _pb(7, graph)


class MatMulInteger:
    """int32-accumulating products of unsigned bytes: onnxruntime's MatMulInteger (uint8 by uint8, the pair every
    onnxruntime version implements, and one whose kernels add the byte products in 32 bits) where onnxruntime is
    installed, else NumPy int32 (a stand-in, named "i8-numpy")."""

    def __init__(self):
        try:
            import onnxruntime as ort
        except ImportError:
            self.name, self.s = "i8-numpy", None
            return
        self.name = "i8-onnxruntime-%s" % ort.__version__
        self.s = ort.InferenceSession(_mmi_model(2, 2), providers=["CPUExecutionProvider"])

    def __call__(self, a, b):
        assert a.dtype == np.uint8 and b.dtype == np.uint8
        if self.s is None:
            return (a.astype(np.int32) @ b.astype(np.int32)).astype(np.int64)
        return self.s.run(None, {"A": a, "B": b})[0].astype(np.int64)


T3_DIR = os.environ.get("EXACT_LLM_T3", os.path.join(CACHE, "t3"))   # the compiled kernel and the weight streams
T3_THREADS = int(os.environ.get("EXACT_LLM_T3_THREADS", "0")) or os.cpu_count() or 1


class T3:
    """The t3 route's kernel, t3.c, compiled once with the C compiler `cc` (or $CC) into T3_DIR and opened with
    ctypes. Matrix products (mm) and element-wise products (mul) by add, subtract, shift by a constant and bitwise
    logic. A registered weight matrix is compiled to its stream once and kept in T3_DIR (2 bytes per nonzero digit
    plus 16 words per output row); any other right operand is recoded at each product. Counters per kind: digit
    adds and subtracts, Horner adds, values recoded, recoding operations."""
    KINDS = ("weights", "peeled", "attention", "element-wise", "weight streams, built once")

    def __init__(self):
        import ctypes
        import subprocess
        src = os.path.join(HERE, "t3.c")
        tag = hashlib.sha256(open(src, "rb").read()).hexdigest()[:12]
        os.makedirs(T3_DIR, exist_ok=True)
        self.path = os.path.join(T3_DIR, "t3-%s.%s" % (tag, "dylib" if sys.platform == "darwin" else "so"))
        if not os.path.exists(self.path):
            cc = os.environ.get("CC", "cc")
            subprocess.run([cc, "-O2", "-shared", "-fPIC", "-pthread", src, "-o", self.path + ".part"], check=True)
            os.replace(self.path + ".part", self.path)
        L = self.lib = ctypes.CDLL(self.path)
        i64, p = ctypes.c_int64, ctypes.c_void_p
        L.t3_compile_masks.argtypes = [i64, i64, p, i64, p, p, p, p]
        L.t3_compile_masks.restype = i64
        L.t3_compile_fill.argtypes = [i64, i64, p, p, p]
        L.t3_run.argtypes = [p, p, i64, i64, i64, p, p, i64, p, p]
        L.t3_mul.argtypes = [i64, p, p, p, ctypes.c_uint64, p]
        self.cnt = {k: np.zeros(4, dtype=np.uint64) for k in self.KINDS}
        self.mats = []                                   # registered weights: (first byte, last byte, name, row stride)
        self.rowoffs = {}
        self.buf = np.empty(0, np.uint16)
        self.log = None                                 # a list: one entry per product, when tracing

    @staticmethod
    def ptr(a):
        return a.ctypes.data

    def register(self, W):
        """The int16 weight matrices [in, out] (memory-mapped) whose streams are compiled once and kept."""
        for name, w in W.items():
            if w.dtype == np.int16 and w.ndim == 2:
                self.mats.append((self.ptr(w), self.ptr(w) + w.nbytes, name, w.shape[1]))

    def weight_key(self, b):
        if b.dtype != np.int16 or b.ndim != 2 or b.strides[1] != 2:
            return None
        at = self.ptr(b)
        for lo, hi, name, ld in self.mats:
            if lo <= at < hi and b.strides[0] == 2 * ld and (at - lo) // 2 < ld:
                return name, (at - lo) // 2, b.shape[1]
        return None

    def compile(self, b, kind):
        """b [n_in, M] (|entries| <= 2^15 - 1) -> the stream (uint16) and the row offsets (int64 [M + 1])."""
        w = np.ascontiguousarray(b, dtype=np.int32)
        n_in, M = w.shape
        assert n_in < (1 << 14)
        pm, mm = np.empty((M, n_in), np.uint16), np.empty((M, n_in), np.uint16)
        rowoff = np.empty(M + 1, np.int64)
        total = self.lib.t3_compile_masks(n_in, M, self.ptr(w), M, self.ptr(pm), self.ptr(mm), self.ptr(rowoff),
                                          self.ptr(self.cnt[kind]))
        stream = np.empty(total, np.uint16)
        self.lib.t3_compile_fill(n_in, M, self.ptr(pm), self.ptr(mm), self.ptr(stream))
        return stream, rowoff

    def weight_stream(self, key, b):
        name, c0, M = key
        base = os.path.join(T3_DIR, "streams", "%s.c%d.m%d" % (name, c0, M))
        if key not in self.rowoffs:
            if not (os.path.exists(base + ".words") and os.path.exists(base + ".rowoff.npy")):
                os.makedirs(os.path.dirname(base), exist_ok=True)
                stream, rowoff = self.compile(b, "weight streams, built once")
                with open(base + ".words.part", "wb") as f:
                    f.write(stream.astype("<u2").tobytes())
                os.replace(base + ".words.part", base + ".words")
                with open(base + ".rowoff.part", "wb") as f:
                    np.save(f, rowoff)
                os.replace(base + ".rowoff.part", base + ".rowoff.npy")
            self.rowoffs[key] = np.load(base + ".rowoff.npy")
        rowoff = self.rowoffs[key]
        n = int(rowoff[-1])
        if self.buf.size < n:                            # one buffer for every stream: read, not kept
            self.buf = np.empty(n, np.uint16)
        with open(base + ".words", "rb") as f:
            assert f.readinto(memoryview(self.buf[:n]).cast("B")) == 2 * n
        return self.buf, rowoff

    def run(self, stream, rowoff, x, kind, threads):
        """y [M, N] (int64) from the stream and x int32 [n_in, N]; the lanes padded with zeros to a multiple of 8."""
        M, N = rowoff.shape[0] - 1, x.shape[1]
        Np = -(-N // 8) * 8
        if Np != N:
            x = np.concatenate([x, np.zeros((x.shape[0], Np - N), np.int32)], 1)
        y = np.empty((M, Np), np.int64)
        if threads > 1:                                  # rows split at equal shares of the stream's words
            part = np.searchsorted(rowoff, np.linspace(0, rowoff[-1], threads + 1)).astype(np.int64)
            part[0], part[-1] = 0, M
        else:
            part = np.array([0, M], np.int64)
        before = self.cnt[kind].copy()
        self.lib.t3_run(self.ptr(stream), self.ptr(rowoff), x.shape[0], Np, N, self.ptr(x), self.ptr(y),
                        part.size - 1, self.ptr(part), self.ptr(self.cnt[kind]))
        if self.log is not None:
            d = self.cnt[kind] - before
            self.log.append((kind, x.shape[0], M, N, int(d[0]), int(d[1])))
        return y[:, :N]

    def mm2(self, a, b):
        N, n_in = a.shape
        M = b.shape[1]
        if N == 0 or M == 0:
            return np.zeros((N, M), np.int64)
        x = np.ascontiguousarray(a.T, dtype=np.int32)
        key = self.weight_key(b)
        if key is not None:
            stream, rowoff = self.weight_stream(key, b)
            return self.run(stream, rowoff, x, "weights", T3_THREADS).T
        stream, rowoff = self.compile(b, "attention")
        return self.run(stream, rowoff, x, "attention", 1).T

    def mm(self, a, b):
        """a @ b exactly (int64) for integer arrays with |entries| <= 2^15 - 1, a [..., N, n], b [..., n, M]."""
        a, b = np.asarray(a), np.asarray(b)
        if a.ndim == 2 and b.ndim == 2:
            return self.mm2(a, b)
        lead = np.broadcast_shapes(a.shape[:-2], b.shape[:-2])
        a = np.broadcast_to(a, lead + a.shape[-2:])
        b = np.broadcast_to(b, lead + b.shape[-2:])
        out = np.empty(lead + (a.shape[-2], b.shape[-1]), np.int64)
        for i in np.ndindex(*lead):
            out[i] = self.mm2(a[i], b[i])
        return out

    def mul(self, a, b, kind="element-wise"):
        """a * b element-wise (int64, broadcast), the operand of smaller magnitude recoded into signed digits."""
        a, b = np.broadcast_arrays(np.asarray(a, dtype=np.int64), np.asarray(b, dtype=np.int64))
        out = np.empty(a.shape, np.int64)
        if a.size == 0:
            return out
        ma, mb = int(np.abs(a).max()), int(np.abs(b).max())
        if ma < mb:
            a, b, mb = b, a, ma
        assert mb < (1 << 62)
        a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
        self.lib.t3_mul(a.size, self.ptr(a), self.ptr(b), self.ptr(out), 1 << mb.bit_length(), self.ptr(self.cnt[kind]))
        return out


_T3 = []


def t3_kernel():
    if not _T3:
        _T3.append(T3())
    return _T3[0]


def mm16(a, b, route, mmi=None):
    """a @ b exactly, as int64, for integer arrays with every |entry| <= 2^15 - 1 (a [..., N, n], b [..., n, M]).
    f64: one float64 product, |partial sums| <= n 2^30 < 2^53.
    f32: a = 256 a1 + a0 with a0 in [-128, 127], a1 in [-128, 128], the same for b; four float32 products in chunks
         of 1,024 inputs, |partial sums| <= 1024 x 2^14 = 2^24; the chunks added in int64.
    i8:  unsigned: u = a + 2^15 in [1, 2^16 - 1], u = 256 u1 + u0 with u1, u0 in [0, 255] (uint8), the same for b;
         four int32 MatMulInteger products of uint8 by uint8, partial sums <= n 255^2 < 2^31; then, in int64,
         a b = u_a u_b - 2^15 (row sums of a) - 2^15 (column sums of b) - n 2^30.
    Then a b (u_a u_b on the i8 route) = 2^16 G11 + 2^8 (G10 + G01) + G00, G_ij = a_i b_j, in int64.
    t3:  b in signed digits (non-adjacent form, positions 0 to 15), each column of b a stream of ADD i, SUB i and
         STEP words; t3.c runs the stream on the columns of a with adds and subtracts only (class T3)."""
    n = a.shape[-1]
    if route == "f64":
        return (a.astype(np.float64) @ b.astype(np.float64)).astype(np.int64)
    if route == "t3":
        return t3_kernel().mm(a, b)
    # the digits in the operand's own type when it is int16 (the weights: no widening; every step below stays within
    # [-2^15, 2^15)), else in int64
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b) if np.asarray(b).dtype == np.int16 else np.asarray(b, dtype=np.int64)
    if route == "f32":
        def bal(x):                                   # x = 256 x1 + x0: x0 = (x & 255) - 256 [x & 255 >= 128]
            x0 = ((x & 255) ^ 128) - 128
            return (x >> 8) + (x0 < 0), x0
        (a1, a0), (b1, b0) = bal(a), bal(b)
        f = lambda x: x.astype(np.float32)
        G = lambda x, y: sum((f(x[..., s:s + CHUNK32]) @ f(y[..., s:s + CHUNK32, :])).astype(np.int64)
                             for s in range(0, n, CHUNK32))
    elif route == "i8":
        assert n <= N_I8
        ua = a + (1 << 15)                                                    # int64, in [1, 2^16 - 1]
        ub = (b.view(np.uint16) ^ 0x8000) if b.dtype == np.int16 else b + (1 << 15)   # int16: b + 2^15, mod 2^16
        a1, a0, b1, b0 = (ua >> 8).astype(np.uint8), (ua & 255).astype(np.uint8), \
            (ub >> 8).astype(np.uint8), (ub & 255).astype(np.uint8)
        U = (mmi(a1, b1) << 16) + ((mmi(a1, b0) + mmi(a0, b1)) << 8) + mmi(a0, b0)   # sum u_a u_b, exact
        ra = a.sum(axis=-1, keepdims=True)                                    # [..., N, 1]
        cb = b.sum(axis=-2, dtype=np.int64, keepdims=True)                    # [..., 1, M]
        return U - ((ra + cb) << 15) - (n << 30)
    else:
        raise SystemExit("unknown route " + route)
    return (G(a1, b1) << 16) + ((G(a1, b0) + G(a0, b1)) << 8) + G(a0, b0)


def peel_bits(n):
    """Index bits of the peel key for rows of n values: 11 up to 2,048 (the 135M's keys), more for wider rows."""
    return max(11, (n - 1).bit_length())


def peel_index(x, k):
    """The k largest |x| of each row, ties to the lower index: unique keys |x| 2^b + (2^b - 1 - i), b = peel_bits(n),
    so the set does not depend on the selection algorithm (|x| 2^b below 2^63: bounds16.py)."""
    n = x.shape[-1]
    b = peel_bits(n)
    key = (np.abs(x) << b) + ((1 << b) - 1 - np.arange(n))
    return np.argpartition(-key, k - 1, axis=-1)[:, :k]


def shmax(c):
    """Largest block shift for integers within [-c, c]: bitlen(c) - 15, plus one for the rounding."""
    return max(0, c.bit_length() - (B16 - 1)) + 1


SITE16 = {"q_proj": "attention input", "k_proj": "attention input", "v_proj": "attention input",
          "o_proj": "o input", "gate_proj": "mlp input", "up_proj": "mlp input", "down_proj": "down input",
          "embed_tokens": "logits input"}


def weight_stats16():
    """Per matrix kind, from the 16-bit weights and their row scales g: inputs n, the largest sum of |w16| over one
    output's inputs (col), the g range, and lin = max over outputs of col 2^(g_max - g), so that an output is at
    most (input bound) lin 2^-g_max. Computed once and kept beside the weights (stats16.json); each matrix is
    opened on its own and let go, so at most one is in memory."""
    d = os.path.join(MCACHE, "int16-rows")
    path = os.path.join(d, "stats16.json")
    if os.path.exists(path):
        return json.load(open(path))
    int16_weights()
    st = {}
    for kind in SITE16:
        names = sorted(f[:-4] for f in os.listdir(d) if f.endswith("." + kind + ".weight.npy"))
        gs = [np.load(os.path.join(d, n + ".g.npy")) for n in names]
        gmin, gmax = min(int(g.min()) for g in gs), max(int(g.max()) for g in gs)
        col, lin, n_in = 0, 0, None
        for name, g in zip(names, gs):
            w = np.load(os.path.join(d, name + ".npy"), mmap_mode="r")
            n_in = w.shape[0]
            for s in range(0, w.shape[1], 8192):
                c = np.abs(np.asarray(w[:, s:s + 8192], dtype=np.int64)).sum(axis=0)
                col = max(col, int(c.max()))
                lin = max(lin, int((c << (gmax - g[s:s + 8192].astype(np.int64))).max()))   # below 2^41
            del w
        st[kind] = {"site": SITE16[kind], "inputs": int(n_in), "matrices": len(names),
                    "col": col, "g_min": gmin, "g_max": gmax, "lin": lin}
    json.dump(st, open(path, "w"), indent=1)
    return st


def bounds16_rows(C, st):
    """The int64 operations of exact-16 that depend on the clamps C (integers at 2^-16, per site), each with its
    largest magnitude and its limit, from the weight statistics st. The clamp rule and bounds16.py use these."""
    rows = []
    lin_out = {}
    for kind, k in st.items():
        c = C[k["site"]]
        sh = shmax(c)
        T = k["col"] * (c + (1 << (sh - 1))) + (1 << (k["g_max"] - 1))     # 2^sh x16 . w16 + peeled + rounding
        lin_out[kind] = ((k["lin"] * (c + (1 << (sh - 1)))) >> k["g_max"]) + 1
        rows.append(("%s: 2^sh x16 . w16 plus the peeled terms (sh <= %d), plus rounding constant" % (kind, sh),
                     T, 1 << 62, k["site"]))
        rows.append(("%s: largest output" % kind, lin_out[kind], 1 << 62, k["site"]))
        b = peel_bits(k["inputs"])
        rows.append(("%s: peel key |x| 2^%d + index" % (kind, b), (c << b) + (1 << b), 1 << 63, k["site"]))
    for kind in ("q_proj", "k_proj"):
        rows.append(("rope: %s output times cos, two terms" % kind, 2 * lin_out[kind] << ROPE, 1 << 63,
                     st[kind]["site"]))
    qk = HEAD * LIM16 * LIM16 << (shmax(C["q"]) + shmax(C["k"]))
    rows.append(("scores: q16 . k16 shifted by sh_q + sh_k, at 2^-32; max minus score", 2 * qk, 1 << 63, "q, k"))
    rows.append(("v: the high half |v >> 15| <= 2^15 - 1", (C["v"] >> (B16 - 1)) + 1, 1 << (B16 - 1), "v"))
    sp = ((1 << A) + ROPE_POS) // 2                                          # sum of p at 2^-15 over one row
    rows.append(("context: 2^15 p16 . vh + p16 . vl", sp * (((C["v"] >> (B16 - 1)) + 1) << (B16 - 1)) + sp * LIM16,
                 1 << 63, "v"))
    rows.append(("gate times up: silu(g) u, both clamped", C["gate"] * C["up"], 1 << 63, "gate, up"))
    rows.append(("rms: max |x| below 2^(NORM_BITS + 16), so the shift is at most 16", C["residual"],
                 1 << (NORM_BITS + A), "residual"))
    rows.append(("residual: clamp plus one linear output", C["residual"] + max(lin_out[k] for k in ("o_proj", "down_proj")),
                 1 << 63, "residual"))
    return rows, lin_out


def clamps16(st):
    """The exact-16 clamps, in real units, by rule: for each site the largest power of two at which every row of
    bounds16_rows below its limit still holds, the others held at 2^0; q and k together, gate and up together."""
    groups = [("residual",), ("attention input",), ("o input",), ("mlp input",), ("down input",),
              ("logits input",), ("q", "k"), ("v",), ("gate", "up")]
    sites = [s for g in groups for s in g]
    e = {s: 0 for s in sites}

    def ok(group, x):
        C = {s: 1 << (e[s] + A) for s in sites}
        for s in group:
            C[s] = 1 << (x + A)
        rows, _ = bounds16_rows(C, st)
        return all(v < lim for _, v, lim, _ in rows)
    for g in groups:
        assert ok(g, 0), g
        x = 0
        while x < 46 and ok(g, x + 1):
            x += 1
        for s in g:
            e[s] = x
    return {s: 1 << e[s] for s in sites}


class Exact16(Exact):
    def __init__(self, route="f64"):
        self.stats16 = weight_stats16()
        self.W16 = int16_weights()
        super().__init__(W=int_weights(small=True), clamps=clamps16(self.stats16))
        self.route = route
        self.mmi = MatMulInteger() if route == "i8" else None
        self.extra = 0                                   # vectors whose rounding needed one more shift
        self.p_held = 0                                  # p values held at 2^15 - 1
        if route == "t3":
            self.t3 = t3_kernel()
            self.t3.register(self.W16)

    def mul(self, a, b, kind="element-wise"):
        return self.t3.mul(a, b, kind) if self.route == "t3" else a * b

    def prepare(self, x, site):
        """A product input as every product that reads it needs it, made once: clamped at its site, its PEEL16
        largest |x| taken out whole (ties to the lower index), the rest block-shifted to 16 bits per vector."""
        x = self.clamp(x, site)
        idx = peel_index(x, PEEL16)
        xp = np.take_along_axis(x, idx, -1)
        x = x.copy()
        np.put_along_axis(x, idx, 0, -1)
        xb, sh, n = block16(x)
        self.extra += n
        return idx, xp, xb, sh

    def product(self, prep, name, dtype=np.int64):
        """prep: an input as prepare() made it, from x int64 [N, in] at 2^-16; the matrix `name`; y at 2^-16:
        y = round(2^-g (2^sh x16 . w16 + sum of the peeled x w16))."""
        idx, xp, xb, sh = prep
        w, g = self.W16[name], self.W16[name + ".g"]
        y = np.empty((xb.shape[0], w.shape[1]), dtype=dtype)
        for c in range(0, w.shape[1], 8192):                                  # output columns in blocks of 8,192
            wc = w[:, c:c + 8192]                                             # int16, memory-mapped
            T = np.left_shift(mm16(xb, wc, self.route, self.mmi), sh)
            for j in range(PEEL16):
                T += self.mul(xp[:, j:j + 1], wc[idx[:, j]], "peeled")         # int64 times int16: int64
            blk = shift_round(T, g[None, c:c + 8192])
            assert dtype == np.int64 or np.abs(blk).max() < (1 << 31)
            y[:, c:c + 8192] = blk
        return y

    def linear(self, x, name, site):
        """x as prepare() made it for this site."""
        return self.product(x, name)

    def logits(self, h):
        return self.product(self.prepare(h, "logits input"), "model.embed_tokens.weight", np.int32)

    def cache_entry(self, k, v):
        """What the cache keeps for each new position, made once: k clamped and block-shifted per head vector (k16
        and its shift), v clamped and split in two 16-bit halves, v = 2^15 vh + vl, vl in [0, 2^15 - 1], |vh| <= 2^13
        within the clamp."""
        kb, shk, n = block16(self.clamp(k, "k"))
        self.extra += n
        v = self.clamp(v, "v")
        vh, vl = v >> (B16 - 1), v & LIM16
        assert (np.abs(vh) <= LIM16).all()
        return kb, shk, vh, vl

    def attention(self, q, kb, shk, vh, vl, kvalid):
        """As Exact's, with q k^T and p v as 16-bit products (k16, its shifts and the halves of v from the cache).
        Scores at 2^-32, p at 2^-15."""
        B, _, L, _ = q.shape
        T, G = kb.shape[2], HEADS // KV
        qb, shq, n1 = block16(self.clamp(q, "q"))                            # per head vector
        qb = qb.reshape(B, KV, G * L, HEAD)
        S = mm16(qb, kb.swapaxes(-1, -2), self.route, self.mmi).reshape(B, KV, G, L, T)
        s = np.left_shift(S, shq.reshape(B, KV, G, L, 1) + shk[:, :, None].swapaxes(-1, -2))
        key = kvalid[:, None, None]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - s, 0) >> (A + 3)
        e = np.where(key, self.exp(t), 0)
        p = shift_round(fdiv(e << A, e.sum(-1, keepdims=True)), 1)            # at 2^-15
        self.p_held += int((p > LIM16).sum())
        pb = np.minimum(p, LIM16).reshape(B, KV, G * L, T)
        self.extra += n1
        c = np.left_shift(mm16(pb, vh, self.route, self.mmi), B16 - 1) + mm16(pb, vl, self.route, self.mmi)
        ctx = shift_round(c, B16 - 1)                                         # 2^-15 x 2^-16 -> 2^-16
        return ctx.reshape(B, KV, G, L, HEAD).reshape(B, HEADS, L, HEAD)


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
    if name in ("exact16-" + r for r in ROUTES + ROUTES_T3):
        return Exact16(name.split("-")[1])
    if name == "float32":
        return Float32()
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


def expected(bits=None):
    """The pinned pair: expected.sha256 (exact) and expected-16.sha256 (exact-16) for the default model;
    expected-16-<model>.sha256 for another."""
    path = os.path.join(HERE, "expected%s%s.sha256" % ("" if bits is None else "-%d" % bits, SUFFIX))
    if not os.path.exists(path):
        return None
    lines = open(path).read().split("\n")
    return lines[0].split()[0], lines[1].split()[0]


def peaks_line(eng):
    return "; ".join("%s %.3f / %s" % (k, v / 2.0 ** A, eng.clamps[k]) for k, v in sorted(eng.peak.items()))


def peaks_record(eng):
    """The measured peaks, clamps and clamped counts of a run, per site, in real units (for bounds16.py)."""
    return {"model": MODEL, "sites": {k: {"peak": v / 2.0 ** A, "clamp": eng.clamps[k],
                                          "margin_log2": round(math.log2(eng.clamps[k] * 2.0 ** A / v), 3) if v else None,
                                          "clamped": eng.clamped.get(k, 0)} for k, v in sorted(eng.peak.items())}}


def main(argv):
    arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    if "--model" in argv:
        use_model(arg("--model", MODELS[0]))
    if len(argv) > 1 and argv[1] == "hash":
        name, batch, threads = arg("--engine", "exact"), int(arg("--batch", "8")), int(arg("--threads", "0"))
        save = arg("--save", None)
        eng = Exact(keep_f64=True) if name == "exact" and "--keep" in argv else engine(name, threads)
        hl, hc, cont, kept = prompt_run(eng, batch, keep=save is not None)
        print("%s %s %s batch=%d" % (hl, hc, name, batch))
        if save:
            np.save(save + ".logits.npy", np.concatenate(kept))
            np.save(save + ".cont.npy", np.array(cont, dtype=np.int32))
        if name.startswith("exact"):
            print("clamped", sum(eng.clamped.values()), eng.clamped)
            print("peaks (real) and clamps:", peaks_line(eng))
            if arg("--peaks", None):
                json.dump(peaks_record(eng), open(arg("--peaks", None), "w"), indent=1)
        if name.startswith("exact16"):
            print("route %s; vectors with one more shift %d; p held at 2^15 - 1: %d" % (
                eng.mmi.name if eng.mmi else eng.route, eng.extra, eng.p_held))
            if eng.route == "t3":
                print("t3 counters (digit adds, Horner adds, values recoded, recoding operations):",
                      {k: [int(v) for v in c] for k, c in eng.t3.cnt.items()})
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
        try:
            import onnxruntime
            ort_version = onnxruntime.__version__
        except ImportError:
            ort_version = "not installed (the i8 route uses NumPy int32)"
        print("versions: Python %s, NumPy %s, onnxruntime %s; %s %s" % (
            sys.version.split()[0], np.__version__, ort_version, sys.platform, os.uname().machine
            if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE", "")))
        print("model %s @ %s: %d layers, width %d, %d/%d heads, feed-forward %d, rotary base %d, %d weights" % (
            MODEL, PIN["revision"][:7], LAYERS, HIDDEN, HEADS, KV, FF, THETA, n_params()))
        t_all = time.time()
        ok, runs = True, []                                    # runs: (name, logits, continuations) for the distance
        if MODEL == MODELS[0]:                                 # the exact engine runs on the default model only
            ex = Exact()
            hl, hc, cont_e, lg_e = prompt_run(ex, 8, keep=True)
            el, ec = expected()
            ok = hl == el and hc == ec
            print("exact    logits %s  continuations %s  %s" % (hl, hc, "MATCH" if ok else "DIFFERENT"))
            print("         clamped values: %d" % sum(ex.clamped.values()))
            runs.append(("exact", lg_e, cont_e))
            del ex
        t0 = time.time()
        weight_stats16()
        int_weights(small=True)
        print("exact16  16-bit weights, int32 embedding and norms, weight statistics: ready in %.0f s" % (time.time() - t0))
        e16 = expected(16)
        if e16 is None:
            print("exact16  no expected-16%s.sha256: the hashes below are not compared" % SUFFIX)
        kept16 = False
        for r in arg("--routes", ",".join(ROUTES)).split(","):
            m16 = Exact16(r)
            t0 = time.time()
            h16l, h16c, cont, lg = prompt_run(m16, 8, keep=not kept16)
            ok16 = (h16l, h16c) == e16
            ok = ok and ok16
            print("exact16  logits %s  continuations %s  %s  route %s, %.0f s, clamped %d" % (
                h16l, h16c, "MATCH" if ok16 else "DIFFERENT", m16.mmi.name if m16.mmi else r, time.time() - t0,
                sum(m16.clamped.values())))
            if r == "t3":
                print("         t3 kernel %s; digit adds, Horner adds, values recoded, recoding operations: %s" % (
                    os.path.basename(m16.t3.path), "; ".join("%s %s" % (k, ", ".join("{:,}".format(int(v)) for v in c))
                                                             for k, c in m16.t3.cnt.items())))
            if not kept16:
                print("         peaks (real) / clamps: %s" % peaks_line(m16))
                if arg("--peaks", None):
                    json.dump(peaks_record(m16), open(arg("--peaks", None), "w"), indent=1)
                runs.append(("exact16", lg, cont))
                kept16 = True
            del m16
        if "--no-float" not in argv:
            t0 = time.time()
            f = Float32()
            fl, fc, cont_f, lg_f = prompt_run(f, 8, keep=True)
            print("float32  logits %s  continuations %s  %.0f s%s" % (
                fl, fc, time.time() - t0, ", matrices widened from bfloat16 at each use" if f.lean else ""))
            del f
            g = np.concatenate(lg_f).astype(np.float64)
            for nm, lg, cont in runs:
                e = np.concatenate(lg).astype(np.float64) / 2.0 ** A
                print("%s against float32 over %d prompt positions: top-1 agreement %d, largest |logit difference| "
                      "%.5f, mean %.6f; continuations equal %d of %d" % (
                          nm, e.shape[0], int((e.argmax(-1) == g.argmax(-1)).sum()), np.abs(e - g).max(),
                          np.abs(e - g).mean(), sum(a == b for a, b in zip(cont, cont_f)), len(cont)))
                del e
            del g, lg_f
        if "--no-float" not in argv and "--no-onnx" not in argv:
            t0 = time.time()
            try:
                o = Onnx()
            except ImportError:
                print("onnx     onnxruntime is not installed here")
            except LookupError as why:
                print("onnx     skipped: %s" % why)
            else:
                ol, oc, _, _ = prompt_run(o, 8)
                print("onnx     logits %s  continuations %s  %.0f s" % (ol, oc, time.time() - t0))
                del o
        print("check    %s, %.0f s" % ("every pair MATCH" if ok else "a pair DIFFERENT or not pinned", time.time() - t_all))
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
