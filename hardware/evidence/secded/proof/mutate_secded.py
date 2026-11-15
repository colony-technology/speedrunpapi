"""Negative controls for proof/independent_secded_checker.py.

    python3 proof/mutate_secded.py [N_K]        (default 72_64)

1. Netlists: for every LUT of the encoder, the syndrome generator and the corrector, one mutant with the first
   row of its table removed.  Each must be rejected, or, if accepted, compute the same function: every output of
   these blocks depends on at most 9 inputs in the corrector, and is linear in the other two, so "same function"
   is decided here exhaustively over each output's inputs (corrector) or by the checker's forms (encoder, syndrome).
2. Matrix: the source text with one data column replaced (a) by an even-weight value, (b) by a copy of another
   column, (c) by zero.  Each must fail condition M.
"""
import importlib.util
import itertools
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("chk", ROOT / "proof" / "independent_secded_checker.py")
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)
import sys as _sys
CODE = _sys.argv[1] if len(_sys.argv) > 1 else "72_64"          # n_k
N = CODE.split("_")[0]
SRC = ROOT / "source" / ("prim_secded_%s_dec.sv" % CODE)
F = {b: ROOT / "proof" / ("colony_secded%s_%s.blif" % (N, b)) for b in ("enc", "syn", "cor")}


def accepted(paths, src=SRC):
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-I", str(ROOT / "proof" / "independent_secded_checker.py"), "--source", str(src),
                        "--enc", str(paths["enc"]), "--syn", str(paths["syn"]), "--cor", str(paths["cor"])], capture_output=True, text=True)
    return r.returncode == 0


def same_corrector(a, b):
    ia, oa, la = chk.parse(a)
    ib, ob, lb = chk.parse(b)
    for o in oa:
        leaves = sorted(chk.cone(la, o) | chk.cone(lb, o))
        for bits in itertools.product((0, 1), repeat=len(leaves)):
            val = {v: 0 for v in ia}
            val.update(dict(zip(leaves, bits)))
            if chk.simulate(la, val)[o] != chk.simulate(lb, val)[o]:
                return False
    return True


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    base = accepted(F)
    print("original accepted:", base)
    fail = not base
    for blk in ("enc", "syn", "cor"):
        lines = F[blk].read_text().split("\n")
        heads = [i for i, l in enumerate(lines) if l.startswith(".names ") and len(l.split()) > 2
                 and not (len(l.split()) == 3 and lines[i + 1] == "1 1")]
        rej = eq = un = 0
        for h in heads:
            m = tmp / ("%s_%d.blif" % (blk, h))
            m.write_text("\n".join(lines[:h + 1] + lines[h + 2:]))
            if not accepted(dict(F, **{blk: m})):
                rej += 1
            elif blk == "cor" and same_corrector(F[blk], m):
                eq += 1
            else:
                un += 1
        fail |= un > 0
        print("%s: %d LUT mutants, %d rejected, %d accepted and equal to the original, %d accepted and different" % (blk, len(heads), rej, eq, un))
    text = SRC.read_text()
    found = [(int(mm.group(1)), int(mm.group(2)), int(mm.group(3), 16)) for mm in re.finditer(r"syndrome_o\[(\d+)\]\s*=\s*\^\(data_i\s*&\s*(\d+)'h([0-9A-Fa-f]+)\)", text)]
    n, nr = found[0][1], len(found)
    rows = {i: v for i, _, v in found}
    col = [sum(((rows[i] >> j) & 1) << i for i in range(nr)) for j in range(n)]
    for label, newcol in (("even weight", 0x03), ("copy of column 1", col[1]), ("zero", 0x00)):
        r2 = dict(rows)
        for i in range(nr):
            r2[i] = (r2[i] & ~1) | ((newcol >> i) & 1)            # replace column 0
        t2 = text
        for i in range(nr):
            t2 = re.sub(r"(syndrome_o\[%d\]\s*=\s*\^\(data_i\s*&\s*%d'h)[0-9A-Fa-f]+" % (i, n), lambda mm: mm.group(1) + "%0*X" % ((n + 3) // 4, r2[i]), t2)
        p = tmp / ("src_%s.sv" % label.replace(" ", "_"))
        p.write_text(t2)
        acc = accepted(F, p)
        fail |= acc
        print("matrix with column 0 replaced by %s: %s" % (label, "accepted   <-- WRONG" if acc else "rejected"))
    raise SystemExit(1 if fail else 0)
