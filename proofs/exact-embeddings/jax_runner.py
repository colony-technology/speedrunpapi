"""The exact model of exact_embed.py, executed by JAX in int64, on CPU or GPU.

The same integer semantics, written again with jax.numpy: every tensor is int64 (jax_enable_x64), every product is an
integer einsum, the tables are gathers, the square root is digit by digit, divisions are floor divisions. There is
no floating point on this path at all. bounds.json gives the int64 headroom of every product and sum. The weights are
the integers exact_embed.py rounds from the published float32 values. The result must have the SHA-256 in
expected.sha256, the same as the NumPy executor's.

usage: python jax_runner.py [--device cpu|gpu] [--batch N]
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_embed as X  # noqa: E402

import jax  # noqa: E402

jax.config.update("jax_enable_x64", True)
import jax.numpy as jnp  # noqa: E402

I64 = jnp.int64


def rshift_round(v, k):
    return (v + (1 << (k - 1))) >> k


def isqrt(n):
    """floor(sqrt(n)) for 0 <= n < 2^62, digit by digit in integers."""
    rem, res, bit = n, jnp.zeros_like(n), 1 << 60
    for _ in range(31):
        t = res + bit
        take = rem >= t
        rem = jnp.where(take, rem - t, rem)
        res = jnp.where(take, (res >> 1) + bit, res >> 1)
        bit >>= 2
    return res


def mm(spec, a, b):
    return jnp.einsum(spec, a, b, preferred_element_type=I64)


def make_forward():
    """Returns forward(W, ids, mask) -> int16 [B, 384], jitted. W, the integer weights and tables as int64 arrays,
    is an argument, not a closure, so the compiled code does not carry the weights as constants."""
    C, CLN, A, WB = X.CLAMP, X.CLAMP_LN, X.A, X.WB

    def linear(x, w, b):
        return rshift_round(mm("ni,io->no", jnp.clip(x, -C, C), w) + b, WB)

    def layernorm(x, g, b):
        x = jnp.clip(x, -CLN, CLN)
        mu = jnp.floor_divide(x.sum(-1, keepdims=True), X.HIDDEN)
        d = x - mu
        var = jnp.floor_divide((d * d).sum(-1, keepdims=True), X.HIDDEN)
        std = isqrt(var + 1)
        y = jnp.floor_divide(d << A, std)
        return rshift_round(y * g, A) + b

    def exp(t, E):
        k = jnp.minimum(t >> X.EXP_STEP, X.EXP_N)
        r = t & ((1 << X.EXP_STEP) - 1)
        e0 = jnp.take(E, k)
        e1 = jnp.take(E, jnp.minimum(k + 1, X.EXP_N))
        return (e0 * ((1 << X.EXP_STEP) - r) + e1 * r) >> X.EXP_STEP

    def gelu(x, G):
        top = X.GELU_N << X.GELU_STEP
        u = x + (X.GELU_LO << A)
        uc = jnp.clip(u, 0, top - 1)
        k, r = uc >> X.GELU_STEP, uc & ((1 << X.GELU_STEP) - 1)
        g = (jnp.take(G, k) * ((1 << X.GELU_STEP) - r) + jnp.take(G, k + 1) * r) >> X.GELU_STEP
        return jnp.where((u >= 0) & (u < top), g, jnp.where(u < 0, 0, x))

    def attention(q, k, v, valid, E):
        q, k, v = (jnp.clip(t, -C, C) for t in (q, k, v))
        s = mm("bhqd,bhkd->bhqk", q, k)
        key = valid[:, None, None, :]
        m = jnp.where(key, s, -(1 << 62)).max(-1, keepdims=True)
        t = jnp.maximum(m - s, 0) >> A
        e = jnp.where(key, exp(t, E), 0)
        p = jnp.floor_divide(e << A, e.sum(-1, keepdims=True))
        return rshift_round(mm("bhqk,bhkd->bhqd", p, v), A)

    def forward(W, ids, mask):
        B, L = ids.shape
        valid = mask.astype(bool)
        x = jnp.take(W["word"], ids, axis=0) + W["pos"][:L][None] + W["typ"][0][None, None]
        x = layernorm(x, W["emb_g"], W["emb_b"])
        split = lambda y: y.reshape(B, L, X.HEADS, X.HEAD).transpose(0, 2, 1, 3)
        for lay in W["layers"]:
            h = x.reshape(B * L, X.HIDDEN)
            q, k, v = (split(linear(h, *lay[n])) for n in ("q", "k", "v"))
            ctx = attention(q, k, v, valid, W["E"]).transpose(0, 2, 1, 3).reshape(B * L, X.HIDDEN)
            x = layernorm((h + linear(ctx, *lay["o"])).reshape(B, L, X.HIDDEN), *lay["ln1"])
            h = x.reshape(B * L, X.HIDDEN)
            o = linear(gelu(linear(h, *lay["i"]), W["G"]), *lay["o2"])
            x = layernorm((h + o).reshape(B, L, X.HIDDEN), *lay["ln2"])
        x = jnp.clip(x, -C, C)
        pooled = jnp.floor_divide((x * valid[..., None]).sum(1), valid.sum(1, keepdims=True).astype(I64))
        norm = isqrt((pooled * pooled).sum(-1, keepdims=True))
        out = jnp.floor_divide(pooled << X.OUT, jnp.maximum(norm, 1))
        return jnp.clip(out, -(1 << X.OUT), (1 << X.OUT) - 1).astype(jnp.int16)

    return jax.jit(forward)


def weights(ex, device):
    put = lambda a: jax.device_put(np.asarray(a, dtype=np.int64), device)
    W = {"word": put(ex.word), "pos": put(ex.pos), "typ": put(ex.typ), "emb_g": put(ex.emb_ln[0]),
         "emb_b": put(ex.emb_ln[1]), "E": put(ex.E), "G": put(ex.G), "layers": []}
    for lay in ex.layers:
        d = {}
        for n in ("q", "k", "v", "o", "i", "o2"):
            wt, b = lay[n]
            d[n] = (put(wt.astype(np.int64)), put(b))        # wt holds integers below 2^53: the cast is exact
        d["ln1"] = (put(lay["ln1"][0]), put(lay["ln1"][1]))
        d["ln2"] = (put(lay["ln2"][0]), put(lay["ln2"][1]))
        W["layers"].append(d)
    return W


def run(device_kind="cpu", batch=32, bucket=8):
    """Embed the 2,758 sentences. Lengths are padded up to a multiple of `bucket` so that few shapes compile;
    padding changes no result (padded keys are masked, padded rows are not pooled)."""
    device = jax.devices(device_kind)[0]
    sentences, _ = X.sentences_and_scores()
    tok = X.tokenizer()
    with jax.default_device(device):
        W = weights(X.Exact(X.load_params()), device)
        fwd = make_forward()
        out = []
        for ids, mask in X.batches(tok, sentences, batch):
            L = -(-ids.shape[1] // bucket) * bucket
            ids = np.pad(ids, ((0, 0), (0, L - ids.shape[1])))
            mask = np.pad(mask, ((0, 0), (0, L - mask.shape[1])))
            out.append(np.asarray(fwd(W, jax.device_put(ids, device), jax.device_put(mask, device))))
    return np.concatenate(out), device


if __name__ == "__main__":
    kind = sys.argv[sys.argv.index("--device") + 1] if "--device" in sys.argv else "cpu"
    batch = int(sys.argv[sys.argv.index("--batch") + 1]) if "--batch" in sys.argv else 32
    t0 = time.time()
    v, dev = run(kind, batch)
    h = X.digest(v)
    print("jax int64 on %s (%s), batch %d: %s  %s  (%.0f s)"
          % (dev.platform, getattr(dev, "device_kind", ""), batch, h, "MATCH" if h == X.expected() else "DIFFERENT",
             time.time() - t0))
