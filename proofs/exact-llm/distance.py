"""How close the exact model is to the float32 model of the same weights, from saved runs.

Prompts (from `exact_llm.py hash --engine E --batch 8 --save DIR/E`): over every prompt position, top-1 agreement, the
largest and the mean |logit difference| (exact logits divided by 2^16), and how many of the 64 continuations of 48
tokens are the same token for token.
Text (from `exact_llm.py text --engine E --save DIR/E`): perplexity of each over the 8,176 predicted tokens of the
16 windows, top-1 agreement at those positions, and the per-token difference of negative log-likelihood.
The same for any pair of engines: `python distance.py DIR exact float32` or `... float32 onnx`.

usage: python distance.py DIR [A B]
"""
import math
import os
import sys

import numpy as np

d = sys.argv[1]
a, b = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("exact", "float32")


def logits(name):
    x = np.load(os.path.join(d, name + ".logits.npy"))
    return x.astype(np.float64) / (2.0 ** 16 if x.dtype == np.int32 else 1.0)


la, lb = logits(a), logits(b)
diff = np.abs(la - lb)
ca, cb = np.load(os.path.join(d, a + ".cont.npy")), np.load(os.path.join(d, b + ".cont.npy"))
first = [int(np.argmax(x != y)) if (x != y).any() else None for x, y in zip(ca, cb)]
print("prompts, %d positions: top-1 agreement %d (%.4f%%); |logit difference| largest %.6f, mean %.7f" % (
    la.shape[0], int((la.argmax(-1) == lb.argmax(-1)).sum()), 100.0 * (la.argmax(-1) == lb.argmax(-1)).mean(),
    diff.max(), diff.mean()))
print("continuations of 48 tokens identical: %d of %d; first differing token of the others at %s" % (
    sum(f is None for f in first), len(first), sorted(f for f in first if f is not None)))
na, nb = np.load(os.path.join(d, a + ".nll.npy")), np.load(os.path.join(d, b + ".nll.npy"))
ta, tb = np.load(os.path.join(d, a + ".top.npy")), np.load(os.path.join(d, b + ".top.npy"))
print("text, %d predicted tokens: perplexity %s %.6f, %s %.6f; top-1 agreement %d (%.4f%%); |nll difference| "
      "largest %.6f, mean %.7f" % (na.size, a, math.exp(na.mean()), b, math.exp(nb.mean()), int((ta == tb).sum()),
                                  100.0 * (ta == tb).mean(), np.abs(na - nb).max(), np.abs(na - nb).mean()))
