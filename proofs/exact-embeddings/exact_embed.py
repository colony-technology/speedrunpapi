"""Exact sentence embeddings: sentence-transformers/all-MiniLM-L6-v2 in integer arithmetic.

Every tensor is an integer array with a power-of-two scale. Element-wise work is NumPy int64. The only floating-point
operation is matrix multiplication, done by the machine's double-precision BLAS on integer-valued arrays; every
partial sum is an integer below 2^53 (bounds.py proves it for the scales below), so the product is exact in any
order, with or without fused multiply-add, on any number of threads. GELU and exp are integer tables
(tables/, made by make_tables.py). The output is 384 int16 per sentence at scale 2^-15.

The same file holds the pinned downloads, a BERT WordPiece tokenizer in plain Python, a plain float32 forward pass
of the same model (the baseline), an onnxruntime baseline, and the STS-B evaluation.

usage:
  python exact_embed.py check                      digests, exact hash against expected.sha256, baselines, STS-B
  python exact_embed.py hash --engine exact|float32|onnx [--batch N] [--threads N]
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

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = json.load(open(os.path.join(HERE, "pins.json")))
CACHE = os.environ.get("EXACT_EMBED_CACHE", os.path.join(HERE, ".cache"))

# ---- scales ---------------------------------------------------------------------------------------------------
A = 16                        # activations: integer x stands for x * 2^-16
WB = 16                       # weights: integer w stands for w * 2^-16; biases at 2^-(A + WB)
CLAMP = 1 << (7 + A)          # every activation is clamped to [-2^7, 2^7] (real units) before a product
CLAMP_LN = 1 << (9 + A)       # LayerNorm inputs are clamped to [-2^9, 2^9]
OUT = 15                      # output: int16 at 2^-15
HEADS, HEAD = 12, 32
HIDDEN = 384
EXP_STEP, EXP_ONE, EXP_N = 8, 24, 24 * 256     # exp table: grid step 2^-8, values at 2^-24, last point 24
GELU_STEP, GELU_LO, GELU_N = 8, 8, 16 * 256    # gelu table: grid step 2^-8 on [-8, 8], values at 2^-16


# ---- downloads ------------------------------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, path, digest):
    """Download url to path unless a file with that SHA-256 is already there; check the digest either way."""
    if not (os.path.exists(path) and sha256_file(path) == digest):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "exact-embeddings"})
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
    url = "https://huggingface.co/%s/resolve/%s/%s" % (m["repo"], m["revision"], name)
    return fetch(url, os.path.join(CACHE, "model", name), m["files"][name])


def sentences_and_scores():
    s = PINS["sentences"]
    url = "https://huggingface.co/datasets/%s/resolve/%s/%s" % (s["repo"], s["revision"], s["file"])
    path = fetch(url, os.path.join(CACHE, "data", s["file"]), s["sha256"])
    rows = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    assert len(rows) == s["pairs"]
    sentences = []
    for r in rows:
        sentences += [r["sentence1"], r["sentence2"]]
    return sentences, np.array([float(r["score"]) for r in rows])


# ---- safetensors, parsed here: 8-byte little-endian header length, JSON header, raw little-endian tensors --------
def read_safetensors(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack("<Q", data[:8])[0]
    header = json.loads(data[8:8 + n].decode("utf-8"))
    header.pop("__metadata__", None)
    base = 8 + n
    out = {}
    for name, t in header.items():
        if t["dtype"] != "F32":
            continue
        b, e = t["data_offsets"]
        count = int(np.prod(t["shape"])) if t["shape"] else 1
        assert e - b == 4 * count
        out[name] = np.frombuffer(data, dtype="<f4", count=count, offset=base + b).reshape(t["shape"])
    return out


# ---- tokenizer: BERT WordPiece, uncased, as in the model's tokenizer_config.json --------------------------------
def _is_whitespace(c):
    return c in " \t\n\r" or unicodedata.category(c) == "Zs"


def _is_control(c):
    return c not in "\t\n\r" and unicodedata.category(c).startswith("C")


def _is_punctuation(c):
    cp = ord(c)
    if 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126:
        return True
    return unicodedata.category(c).startswith("P")


def _is_cjk(cp):
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F
            or 0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF or 0xF900 <= cp <= 0xFAFF
            or 0x2F800 <= cp <= 0x2FA1F)


class Tokenizer:
    def __init__(self, vocab_path, max_len=256):
        self.vocab = {}
        with open(vocab_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                self.vocab[line.rstrip("\n")] = i
        self.max_len = max_len
        self.cls, self.sep, self.unk = self.vocab["[CLS]"], self.vocab["[SEP]"], self.vocab["[UNK]"]

    def basic(self, text):
        out = []
        for c in text:
            cp = ord(c)
            if cp == 0 or cp == 0xFFFD or _is_control(c):
                continue
            if _is_whitespace(c):
                out.append(" ")
            elif _is_cjk(cp):
                out.append(" %s " % c)
            else:
                out.append(c)
        words = []
        for w in "".join(out).split():
            w = w.lower()
            w = "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")
            cur = ""
            for c in w:
                if _is_punctuation(c):
                    if cur:
                        words.append(cur)
                        cur = ""
                    words.append(c)
                else:
                    cur += c
            if cur:
                words.append(cur)
        return words

    def wordpiece(self, word):
        if len(word) > 100:
            return [self.unk]
        pieces, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while start < end:
                sub = word[start:end] if start == 0 else "##" + word[start:end]
                if sub in self.vocab:
                    found = self.vocab[sub]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            pieces.append(found)
            start = end
        return pieces

    def encode(self, text):
        ids = []
        for w in self.basic(text):
            ids += self.wordpiece(w)
        return [self.cls] + ids[: self.max_len - 2] + [self.sep]


def batches(tok, sentences, size):
    for i in range(0, len(sentences), size):
        enc = [tok.encode(s) for s in sentences[i:i + size]]
        L = max(len(e) for e in enc)
        ids = np.zeros((len(enc), L), dtype=np.int64)
        mask = np.zeros((len(enc), L), dtype=np.int64)
        for j, e in enumerate(enc):
            ids[j, :len(e)] = e
            mask[j, :len(e)] = 1
        yield ids, mask


# ---- integer arithmetic ---------------------------------------------------------------------------------------
def rshift_round(v, k):
    """floor(v / 2^k + 1/2): round to nearest, halves up."""
    return (v + (1 << (k - 1))) >> k


def isqrt(n):
    """Exact floor(sqrt(n)) for int64 0 <= n < 2^62: float64 sqrt, then integer correction steps.
    The result s is asserted by its bracket s^2 <= n < (s + 1)^2, the form a proof circuit checks."""
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


def load_table(name):
    with open(os.path.join(HERE, "tables", name)) as f:
        return np.array([int(line) for line in f if not line.startswith("#")], dtype=np.int64)


def round_pow2(a, k):
    """round(a * 2^k), a float32, to the nearest integer (ties to even). Exact: the scaling is exact in float64."""
    return np.rint(a.astype(np.float64) * 2.0 ** k).astype(np.int64)


def round_pow2_over_sqrt32(a, k):
    """round(a * 2^k / sqrt(32)) = round(a * 2^(k-3) * sqrt(2)), in exact integer arithmetic (no ties occur)."""
    m = k - 3
    flat = a.astype(np.float64).ravel().tolist()
    out = np.zeros(len(flat), dtype=np.int64)
    for i, v in enumerate(flat):
        if v == 0.0:
            continue
        num, den = v.as_integer_ratio()
        p, q = (abs(num) << m, den) if m >= 0 else (abs(num), den << -m)
        n = (math.isqrt((8 * p * p) // (q * q)) + 1) // 2          # floor(p sqrt2 / q + 1/2)
        out[i] = n if num > 0 else -n
    return out.reshape(a.shape)


class Exact:
    def __init__(self, params, keep_int=False):
        P = params
        self.word = round_pow2(P["embeddings.word_embeddings.weight"], A)
        self.pos = round_pow2(P["embeddings.position_embeddings.weight"], A)
        self.typ = round_pow2(P["embeddings.token_type_embeddings.weight"], A)
        self.emb_ln = (round_pow2(P["embeddings.LayerNorm.weight"], A), round_pow2(P["embeddings.LayerNorm.bias"], A))
        self.layers = []
        self.int_weights = {}
        for i in range(6):
            p = "encoder.layer.%d." % i
            lay = {}
            for key, name in (("q", "attention.self.query"), ("k", "attention.self.key"),
                              ("v", "attention.self.value"), ("o", "attention.output.dense"),
                              ("i", "intermediate.dense"), ("o2", "output.dense")):
                w, b = P[p + name + ".weight"], P[p + name + ".bias"]
                if key == "q":                       # 1/sqrt(32) folded into the query before rounding
                    wi, bi = round_pow2_over_sqrt32(w, WB), round_pow2_over_sqrt32(b, A + WB)
                else:
                    wi, bi = round_pow2(w, WB), round_pow2(b, A + WB)
                if keep_int:
                    self.int_weights[p + name + ".weight"] = wi
                lay[key] = (np.ascontiguousarray(wi.T).astype(np.float64), bi)
            lay["ln1"] = (round_pow2(P[p + "attention.output.LayerNorm.weight"], A),
                          round_pow2(P[p + "attention.output.LayerNorm.bias"], A))
            lay["ln2"] = (round_pow2(P[p + "output.LayerNorm.weight"], A), round_pow2(P[p + "output.LayerNorm.bias"], A))
            self.layers.append(lay)
        self.E = load_table("exp.txt")
        self.G = load_table("gelu.txt")
        assert len(self.E) == EXP_N + 1 and len(self.G) == GELU_N + 1
        self.clamped = {}
        self.peak = {}

    def clamp(self, x, c, where):
        """Clamp to [-c, c], counting the values that were outside and keeping the largest magnitude seen."""
        a = np.abs(x)
        n = int((a > c).sum())
        if n:
            self.clamped[where] = self.clamped.get(where, 0) + n
        self.peak[where] = max(self.peak.get(where, 0), int(a.max()) if a.size else 0)
        return np.clip(x, -c, c)

    def linear(self, x, wb, where):
        w, b = wb
        y = (self.clamp(x, CLAMP, where).astype(np.float64) @ w).astype(np.int64) + b      # exact, see bounds.py
        return rshift_round(y, WB)

    def layernorm(self, x, gb):
        g, b = gb
        x = self.clamp(x, CLAMP_LN, "layernorm input")
        mu = fdiv(x.sum(-1, keepdims=True), HIDDEN)
        d = x - mu
        var = fdiv((d * d).sum(-1, keepdims=True), HIDDEN)           # at 2^-32
        std = isqrt(var + 1)                                          # at 2^-16; the + 1 is eps = 2^-32
        y = fdiv(d << A, std)
        return rshift_round(y * g, A) + b

    def exp(self, t):
        """E interpolated: t >= 0 at 2^-16; result at 2^-24."""
        k = np.minimum(t >> EXP_STEP, EXP_N)
        r = t & ((1 << EXP_STEP) - 1)
        e0, e1 = self.E[k], self.E[np.minimum(k + 1, EXP_N)]
        return (e0 * ((1 << EXP_STEP) - r) + e1 * r) >> EXP_STEP

    def gelu(self, x):
        """G interpolated on [-8, 8); x outside: 0 below, x above. x and result at 2^-16."""
        u = x + (GELU_LO << A)
        inside = (u >= 0) & (u < (GELU_N << GELU_STEP))
        uc = np.clip(u, 0, (GELU_N << GELU_STEP) - 1)
        k, r = uc >> GELU_STEP, uc & ((1 << GELU_STEP) - 1)
        g = (self.G[k] * ((1 << GELU_STEP) - r) + self.G[k + 1] * r) >> GELU_STEP
        return np.where(inside, g, np.where(u < 0, 0, x))

    def attention(self, q, k, v, valid):
        qc = self.clamp(q, CLAMP, "query").astype(np.float64)
        kc = self.clamp(k, CLAMP, "key").astype(np.float64)
        vc = self.clamp(v, CLAMP, "value").astype(np.float64)
        s = (qc @ kc.swapaxes(-1, -2)).astype(np.int64)              # scores at 2^-32, |s| <= 32 * 2^46
        key = valid[:, None, None, :]
        m = np.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = np.maximum(m - s, 0) >> A                                 # m - s at 2^-16, floor
        e = np.where(key, self.exp(t), 0)                             # at 2^-24
        p = fdiv(e << A, e.sum(-1, keepdims=True))                    # at 2^-16, each row sums to at most 2^16
        ctx = (p.astype(np.float64) @ vc).astype(np.int64)            # at 2^-32, |ctx| <= 2^16 * 2^23
        return rshift_round(ctx, A)

    def forward(self, ids, mask):
        B, L = ids.shape
        valid = mask.astype(bool)
        x = self.word[ids] + self.pos[:L][None] + self.typ[0][None, None]
        x = self.layernorm(x, self.emb_ln)
        for n, lay in enumerate(self.layers):
            h = x.reshape(B * L, HIDDEN)
            split = lambda y: y.reshape(B, L, HEADS, HEAD).transpose(0, 2, 1, 3)
            q = split(self.linear(h, lay["q"], "query input"))
            k = split(self.linear(h, lay["k"], "key input"))
            v = split(self.linear(h, lay["v"], "value input"))
            ctx = self.attention(q, k, v, valid).transpose(0, 2, 1, 3).reshape(B * L, HIDDEN)
            a = self.linear(ctx, lay["o"], "attention output input")
            x = self.layernorm((h + a).reshape(B, L, HIDDEN), lay["ln1"])
            h = x.reshape(B * L, HIDDEN)
            f = self.gelu(self.linear(h, lay["i"], "intermediate input"))
            o = self.linear(f, lay["o2"], "output input")
            x = self.layernorm((h + o).reshape(B, L, HIDDEN), lay["ln2"])
        return self.pool(x, valid)

    def pool(self, x, valid):
        x = self.clamp(x, CLAMP, "pooling input")
        s = (x * valid[..., None]).sum(1)
        pooled = fdiv(s, valid.sum(1, keepdims=True).astype(np.int64))  # mean over the attention mask, floor, 2^-16
        norm = isqrt((pooled * pooled).sum(-1, keepdims=True))        # at 2^-16
        out = fdiv(pooled << OUT, np.maximum(norm, 1))                # floor, 2^-15
        return np.clip(out, -(1 << OUT), (1 << OUT) - 1).astype(np.int16)


# ---- the float32 baseline: a plain forward pass of the same model -------------------------------------------------
def _erf32(x):
    """erf by Abramowitz and Stegun 7.1.26 in float64 (error below 1.5e-7), returned as float32."""
    z = np.abs(x.astype(np.float64))
    t = 1.0 / (1.0 + 0.3275911 * z)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t \
        * np.exp(-z * z)
    return (np.sign(x) * y).astype(np.float32)


class Float32:
    def __init__(self, params):
        self.P = {k: np.ascontiguousarray(v) for k, v in params.items()}
        self.T = {k: np.ascontiguousarray(v.T) for k, v in params.items() if k.endswith(".weight") and v.ndim == 2}

    def ln(self, x, p):
        mu = x.mean(-1, keepdims=True)
        var = ((x - mu) ** 2).mean(-1, keepdims=True)
        return (x - mu) / np.sqrt(var + np.float32(1e-12)) * self.P[p + ".weight"] + self.P[p + ".bias"]

    def lin(self, x, p):
        return x @ self.T[p + ".weight"] + self.P[p + ".bias"]

    def forward(self, ids, mask):
        B, L = ids.shape
        P = self.P
        x = P["embeddings.word_embeddings.weight"][ids] + P["embeddings.position_embeddings.weight"][:L][None] \
            + P["embeddings.token_type_embeddings.weight"][0][None, None]
        x = self.ln(x, "embeddings.LayerNorm")
        neg = ((1.0 - mask.astype(np.float32)) * np.finfo(np.float32).min)[:, None, None, :]
        for i in range(6):
            p = "encoder.layer.%d." % i
            split = lambda y: y.reshape(B, L, HEADS, HEAD).transpose(0, 2, 1, 3)
            q, k, v = (split(self.lin(x, p + "attention.self." + n)) for n in ("query", "key", "value"))
            s = (q @ k.swapaxes(-1, -2)) / np.float32(math.sqrt(HEAD)) + neg
            s = np.exp(s - s.max(-1, keepdims=True))
            ctx = ((s / s.sum(-1, keepdims=True)) @ v).transpose(0, 2, 1, 3).reshape(B, L, HIDDEN)
            x = self.ln(x + self.lin(ctx, p + "attention.output.dense"), p + "attention.output.LayerNorm")
            h = self.lin(x, p + "intermediate.dense")
            h = h * np.float32(0.5) * (np.float32(1.0) + _erf32(h / np.float32(math.sqrt(2.0))))
            x = self.ln(x + self.lin(h, p + "output.dense"), p + "output.LayerNorm")
        return pool_float(x, mask)


def pool_float(x, mask):
    m = mask.astype(np.float32)[..., None]
    pooled = (x * m).sum(1) / np.maximum(m.sum(1), np.float32(1e-9))
    return (pooled / np.maximum(np.linalg.norm(pooled, axis=-1, keepdims=True), np.float32(1e-12))).astype(np.float32)


class Onnx:
    def __init__(self, threads=0):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
            so.inter_op_num_threads = 1
        self.s = ort.InferenceSession(model_file("onnx/model.onnx"), so, providers=["CPUExecutionProvider"])
        self.names = [i.name for i in self.s.get_inputs()]

    def forward(self, ids, mask):
        feed = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        out = self.s.run(None, {k: v for k, v in feed.items() if k in self.names})[0]
        return pool_float(out.astype(np.float32), mask)


# ---- running, hashing, STS-B ----------------------------------------------------------------------------------
def load_params():
    return read_safetensors(model_file("model.safetensors"))


def engine(name, threads=0):
    if name == "exact":
        return Exact(load_params())
    if name == "float32":
        return Float32(load_params())
    if name == "onnx":
        return Onnx(threads)
    raise SystemExit("unknown engine " + name)


def embed(eng, tok, sentences, batch):
    return np.concatenate([eng.forward(ids, mask) for ids, mask in batches(tok, sentences, batch)])


def digest(vectors):
    dt = "<i2" if vectors.dtype == np.int16 else "<f4"
    return hashlib.sha256(np.ascontiguousarray(vectors).astype(dt).tobytes()).hexdigest()


def rankdata(a):
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    end = np.cumsum(counts)
    return ((end - counts + end - 1) / 2.0 + 1.0)[inv]


def spearman(x, y):
    rx, ry = rankdata(x), rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    return float((rx * ry).sum() / math.sqrt((rx * rx).sum() * (ry * ry).sum()))


def pair_cosines(v):
    a, b = v[0::2], v[1::2]
    if v.dtype == np.int16:
        return (a.astype(np.int64) * b.astype(np.int64)).sum(1)      # the integer dot product, cosine * 2^30
    return (a.astype(np.float64) * b.astype(np.float64)).sum(1)


def tokenizer():
    return Tokenizer(model_file("vocab.txt"), max_len=256)


def expected():
    return open(os.path.join(HERE, "expected.sha256")).read().split()[0]


def main(argv):
    if len(argv) > 1 and argv[1] == "hash":
        eng_name = argv[argv.index("--engine") + 1] if "--engine" in argv else "exact"
        batch = int(argv[argv.index("--batch") + 1]) if "--batch" in argv else 32
        threads = int(argv[argv.index("--threads") + 1]) if "--threads" in argv else 0
        sentences, _ = sentences_and_scores()
        v = embed(engine(eng_name, threads), tokenizer(), sentences, batch)
        print("%s %s batch=%d" % (digest(v), eng_name, batch))
        if "--save" in argv:
            np.save(argv[argv.index("--save") + 1], v)
        return 0
    if len(argv) > 1 and argv[1] == "check":
        sentences, gold = sentences_and_scores()
        tok = tokenizer()
        ex = Exact(load_params())
        v = embed(ex, tok, sentences, 32)
        h = digest(v)
        ok = h == expected()
        print("exact    %s  %s" % (h, "MATCH" if ok else "DIFFERENT"))
        print("         clamped values: %d" % sum(ex.clamped.values()))
        f = embed(Float32(load_params()), tok, sentences, 32)
        print("float32  %s" % digest(f))
        try:
            o = embed(Onnx(), tok, sentences, 32)
            print("onnx     %s" % digest(o))
        except ImportError:
            o = None
            print("onnx     onnxruntime is not installed here")
        print("STS-B test, %d pairs, Spearman of cosine against the gold scores:" % len(gold))
        print("  exact    %.4f" % spearman(pair_cosines(v), gold))
        print("  float32  %.4f" % spearman(pair_cosines(f), gold))
        if o is not None:
            print("  onnx     %.4f" % spearman(pair_cosines(o), gold))
        e = v.astype(np.float64) / 2.0 ** OUT
        c = (e * f).sum(1) / np.linalg.norm(e, axis=1) / np.linalg.norm(f.astype(np.float64), axis=1)
        print("cosine between the float32 and the exact vector of each sentence: min %.6f, mean %.6f" % (c.min(), c.mean()))
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
