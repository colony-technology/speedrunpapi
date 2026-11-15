"""Longer continuations: whether the token ids, not only the logits, ever differ.

Runs one engine at one batch size: the 64 prompts, each continued greedily for 256 tokens. Prints the SHA-256 of the
64 x 256 token ids and saves them. With --compare, reads the saved runs and prints, for each pair, how many of the 64
continuations are identical and where the first differing token of each other one is.

usage: python long_run.py exact|exact-lean|float32|onnx BATCH OUTDIR
       python long_run.py --compare OUTDIR
"""
import hashlib
import itertools
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exact_llm as X  # noqa: E402

N = 256
if sys.argv[1] == "--compare":
    d = sys.argv[2]
    runs = {f[:-4]: np.load(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".npy")}
    for a, b in itertools.combinations(sorted(runs), 2):
        x, y = runs[a], runs[b]
        first = [int(np.argmax(r != s)) for r, s in zip(x, y) if (r != s).any()]
        print("%-14s %-14s identical %2d of %d; first differing token of the others at %s" % (
            a, b, len(x) - len(first), len(x), sorted(first)))
    sys.exit(0)
name, batch, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
eng = X.Exact(keep_f64=False) if name == "exact-lean" else X.engine(name)
cont = np.array(X.run_prompts(eng, X.tokenizer(), X.prompts(), batch, gen=N), dtype=np.int32)
os.makedirs(out, exist_ok=True)
np.save(os.path.join(out, "%s-b%d.npy" % (name.replace("-lean", ""), batch)), cont)
print("%s batch %d: %d x %d tokens, SHA-256 %s" % (name, batch, cont.shape[0], cont.shape[1],
                                                    hashlib.sha256(cont.astype("<i4").tobytes()).hexdigest()))
