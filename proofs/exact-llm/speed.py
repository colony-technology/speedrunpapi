"""Tokens a second and peak memory of one engine on this machine.

Prefill: the first text window, 512 tokens, one forward pass. Decode: the first 8 prompts at batch 8 and the first
2 at batch 1, timed with 48 generated tokens and again with 1; the difference is the time of the other 47 per row.
Peak memory is the process's own maximum resident set size. Run each engine in its own process.

usage: python speed.py exact|exact-keep|float32     (exact: one matrix at a time; exact-keep: float64 kept)
"""
import os
import resource
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

name = sys.argv[1]
t0 = time.time()
m = X.Exact(keep_f64=(name == "exact-keep")) if name.startswith("exact") else X.engine(name)
load = time.time() - t0
tok = X.tokenizer()
w = X.text_windows(tok, n=1)[0]
X.run_window(m, w[:, :16])                                     # first use: conversions, caches
t0 = time.time()
X.run_window(m, w)
pre = time.time() - t0
out = ["%s: load %.1f s; prefill %.0f tokens/s (512 tokens in %.2f s)" % (name, load, 512 / pre, pre)]
for batch, n in ((8, 8), (1, 2)):
    p = X.prompts()[:n]
    t0 = time.time()
    X.run_prompts(m, tok, p, batch, gen=1)
    one = time.time() - t0
    t0 = time.time()
    X.run_prompts(m, tok, p, batch, gen=48)
    full = time.time() - t0
    out.append("decode batch %d: %.1f tokens/s (%d rows x 47 tokens in %.2f s)" % (batch, n * 47 / (full - one), n, full - one))
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss                 # bytes on macOS, kilobytes on Linux
out.append("peak resident %.0f MB" % (rss / 2 ** 20 if sys.platform == "darwin" else rss / 2 ** 10))
print("; ".join(out))
