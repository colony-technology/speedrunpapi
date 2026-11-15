"""Build exact_embeddings.ipynb from the files of this folder.

Colab opens a notebook without its folder, so the notebook carries the code and the tables it needs: its first code
cell writes exact_embed.py, jax_runner.py, pins.json, expected.sha256 and the two tables, and checks each by the
SHA-256 recorded here. The notebook needs NumPy only (and JAX, which Colab has, for the GPU cell).

usage: python make_notebook.py            write exact_embeddings.ipynb
       python make_notebook.py --check    rebuild and compare with the notebook in this folder
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["exact_embed.py", "jax_runner.py", "pins.json", "expected.sha256", "tables/exp.txt", "tables/gelu.txt"]

INTRO = (
    "# Exact embeddings\n\n"
    "This notebook downloads the sentence-embedding model all-MiniLM-L6-v2 and the 2,758 sentences of the STS-B test "
    "set at pinned revisions and checks both by SHA-256. "
    "It embeds every sentence with an integer version of the model, in which the only floating-point operation is a "
    "product of integer matrices small enough to be exact in double precision, and with a plain float32 version. "
    "It prints the STS-B Spearman correlation of both and, if the runtime has a GPU and JAX, runs the integer model "
    "on the GPU. "
    "The last cell prints the SHA-256 of the 2,758 integer vectors with MATCH or DIFFERENT against the hash in the "
    "repository, then the SHA-256 of the float32 vectors on this machine.\n")

RUN_EXACT = '''import time
import numpy as np
import exact_embed as X

sentences, gold = X.sentences_and_scores()
tok = X.tokenizer()
t0 = time.time()
exact = X.embed(X.Exact(X.load_params()), tok, sentences, 32)
h = X.digest(exact)
print("exact    %s  %s  (%.0f s)" % (h, "MATCH" if h == X.expected() else "DIFFERENT", time.time() - t0))
print("expected %s" % X.expected())'''

RUN_FLOAT = '''t0 = time.time()
f32 = X.embed(X.Float32(X.load_params()), tok, sentences, 32)
print("float32  %s  (%.0f s)" % (X.digest(f32), time.time() - t0))'''

RUN_STSB = '''print("STS-B test, %d pairs, Spearman of cosine against the gold scores:" % len(gold))
print("  exact    %.4f" % X.spearman(X.pair_cosines(exact), gold))
print("  float32  %.4f" % X.spearman(X.pair_cosines(f32), gold))
e = exact.astype(np.float64) / 2.0 ** X.OUT
c = (e * f32).sum(1) / np.linalg.norm(e, axis=1) / np.linalg.norm(f32.astype(np.float64), axis=1)
print("cosine between the float32 and the exact vector of each sentence: min %.6f, mean %.6f" % (c.min(), c.mean()))'''

RUN_GPU = '''try:
    import jax_runner as J  # sets jax_enable_x64 before any array exists
except ImportError:
    J = None
    print("JAX is not installed here: no GPU run")
gpus = []
if J is not None:
    try:
        gpus = J.jax.devices("gpu")
    except RuntimeError:
        print("no GPU in this runtime: Runtime > Change runtime type > a GPU, then run all cells again")
if gpus:
    v, dev = J.run("gpu", 32)
    h = X.digest(v)
    print("jax int64 on %s  %s  %s" % (dev.device_kind, h, "MATCH" if h == X.expected() else "DIFFERENT"))'''

FINAL = '''h = X.digest(exact)
print("exact    %s  %s" % (h, "MATCH" if h == X.expected() else "DIFFERENT"))
print("float32  %s  (this machine)" % X.digest(f32))'''


def sha(b):
    return hashlib.sha256(b).hexdigest()


def setup_cell():
    lines = ["# The folder's code and tables, written here and checked by SHA-256.",
             "import hashlib, os", "FILES = {}"]
    for name in FILES:
        body = open(os.path.join(HERE, name), encoding="utf-8").read()
        lines.append("FILES[%r] = (%r, %r)" % (name, sha(body.encode("utf-8")), body))
    lines += ["for name, (digest, body) in FILES.items():",
              "    os.makedirs(os.path.dirname(name) or '.', exist_ok=True)",
              "    with open(name, 'w', encoding='utf-8') as f:",
              "        f.write(body)",
              "    assert hashlib.sha256(open(name, 'rb').read()).hexdigest() == digest, name",
              "print('wrote and checked', ', '.join(FILES))"]
    return "\n".join(lines)


def cell(kind, text, n):
    src = text.splitlines(keepends=True)
    c = {"cell_type": kind, "id": "cell-%d" % n, "metadata": {}, "source": src}
    if kind == "code":
        c.update({"execution_count": None, "outputs": []})
    return c


def build():
    cells = [cell("markdown", INTRO, 0), cell("code", setup_cell(), 1), cell("code", RUN_EXACT, 2),
             cell("code", RUN_FLOAT, 3), cell("code", RUN_STSB, 4), cell("code", RUN_GPU, 5),
             cell("code", FINAL, 6)]
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}, "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(nb, indent=1, ensure_ascii=False) + "\n"


def script():
    """The notebook's code cells as one script, to run the notebook outside Jupyter."""
    return "\n\n".join([setup_cell(), RUN_EXACT, RUN_FLOAT, RUN_STSB, RUN_GPU, FINAL]) + "\n"


if __name__ == "__main__":
    path = os.path.join(HERE, "exact_embeddings.ipynb")
    if "--check" in sys.argv:
        assert open(path, encoding="utf-8").read() == build(), "the notebook differs from the folder's files"
        print("exact_embeddings.ipynb: built from the current files")
    elif "--script" in sys.argv:
        sys.stdout.write(script())
    else:
        open(path, "w", encoding="utf-8").write(build())
        print("wrote exact_embeddings.ipynb")
