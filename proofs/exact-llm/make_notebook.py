"""Build exact_llm.ipynb from the files of this folder.

Colab opens a notebook without its folder, so the notebook carries the code and the tables it needs: its first code
cell writes exact_llm.py, pins.json, expected.sha256 and the four tables, and checks each by the SHA-256 recorded
here. The notebook needs NumPy only.

usage: python make_notebook.py            write exact_llm.ipynb
       python make_notebook.py --check    rebuild and compare with the notebook in this folder
       python make_notebook.py --script   print the code cells as one script
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["exact_llm.py", "pins.json", "expected.sha256", "tables/exp.txt", "tables/silu.txt", "tables/cos.txt",
         "tables/sin.txt"]

INTRO = (
    "# Exact inference: SmolLM2-135M\n\n"
    "This notebook downloads the language model SmolLM2-135M and 64 prompts at pinned revisions and checks them by "
    "SHA-256. "
    "It runs every prompt through an integer version of the model, in which the only floating-point operation is a "
    "product of integer matrices small enough to be exact in double precision, and through a plain float32 version "
    "of the same weights. "
    "It prints how close the two are: top-1 agreement over every prompt position, the logit differences, and how "
    "many of the 64 greedy continuations of 48 tokens are the same. "
    "The last cell prints the SHA-256 of the integer logits and continuations with MATCH or DIFFERENT against the "
    "hashes in the repository, then the SHA-256 of the float32 ones on this machine.\n")

RUN_EXACT = '''import time
import numpy as np
import exact_llm as X

t0 = time.time()
ex = X.Exact()
hl, hc, cont_e, lg_e = X.prompt_run(ex, 8, keep=True)
print("exact    logits %s  continuations %s  (%.0f s, %d values clamped)" % (hl, hc, time.time() - t0, sum(ex.clamped.values())))
del ex'''

RUN_FLOAT = '''t0 = time.time()
f = X.Float32(X.read_safetensors(X.model_file("model.safetensors")))
fl, fc, cont_f, lg_f = X.prompt_run(f, 8, keep=True)
print("float32  logits %s  continuations %s  (%.0f s)" % (fl, fc, time.time() - t0))
del f'''

RUN_DIST = '''e = np.concatenate(lg_e).astype(np.float64) / 2.0 ** 16
g = np.concatenate(lg_f).astype(np.float64)
print("over %d prompt positions: top-1 agreement %d; |logit difference| largest %.5f, mean %.6f"
      % (e.shape[0], int((e.argmax(-1) == g.argmax(-1)).sum()), np.abs(e - g).max(), np.abs(e - g).mean()))
print("greedy continuations of 48 tokens identical: %d of %d" % (sum(a == b for a, b in zip(cont_e, cont_f)), len(cont_e)))
tok = X.tokenizer()
dec = {i: t for t, i in tok.vocab.items()}
byte = {c: b for b, c in X._byte_encoder().items()}
text = lambda ids: bytes(byte[c] for i in ids for c in dec[i]).decode("utf-8", "replace")
print("prompt 1: %r -> %r" % (X.prompts()[0], text(cont_e[0])))'''

FINAL = '''el, ec = X.expected()
print("exact    logits %s  continuations %s  %s" % (hl, hc, "MATCH" if (hl, hc) == (el, ec) else "DIFFERENT"))
print("float32  logits %s  continuations %s  (this machine)" % (fl, fc))'''


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
    c = {"cell_type": kind, "id": "cell-%d" % n, "metadata": {}, "source": text.splitlines(keepends=True)}
    if kind == "code":
        c.update({"execution_count": None, "outputs": []})
    return c


CODE = [RUN_EXACT, RUN_FLOAT, RUN_DIST, FINAL]


def build():
    cells = [cell("markdown", INTRO, 0), cell("code", setup_cell(), 1)] + [cell("code", c, i + 2) for i, c in enumerate(CODE)]
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}, "colab": {"provenance": []}},
          "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(nb, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    path = os.path.join(HERE, "exact_llm.ipynb")
    if "--check" in sys.argv:
        assert open(path, encoding="utf-8").read() == build(), "the notebook differs from the folder's files"
        print("exact_llm.ipynb: built from the current files")
    elif "--script" in sys.argv:
        sys.stdout.write("\n\n".join([setup_cell()] + CODE) + "\n")
    else:
        open(path, "w", encoding="utf-8").write(build())
        print("wrote exact_llm.ipynb")
