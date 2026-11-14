"""Text-level tie between NAME_lut6.v and proof/NAME.blif.  Does not use the generator or Yosys.

    python3 proof/lut6_vs_blif.py

For each block: every LUTk instance in NAME_lut6.v, read as  wire W; LUTk #(.INIT(..)) u (.O(W), .I0(a), ..);
must match the BLIF .names line with output W: the same inputs in the same order (I0 = first BLIF input), and
INIT bit r = 1 exactly for the BLIF on-set rows r (row r: input q = bit q of r).  Every BLIF LUT must appear
once, and the assign lines for o[i] must name the same driver as the BLIF output buffer.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["colony_crc32_d8", "colony_crc32_d32", "colony_crc32_d64", "colony_crc32_be64"]


def blif(path):
    luts, cur = {}, None
    for line in path.read_text().replace("\\\n", " ").splitlines():
        t = line.split()
        if not t or t[0] in (".model", ".inputs", ".outputs", ".end"):
            cur = None
            continue
        if t[0] == ".names":
            cur = t[-1]
            luts[cur] = (t[1:-1], 0)
        else:
            src, tt = luts[cur]
            luts[cur] = (src, tt | (1 << sum(1 << q for q, c in enumerate(t[0]) if c == "1")))
    return luts


if __name__ == "__main__":
    bad = 0
    for n in NAMES:
        b = blif(ROOT / "proof" / (n + ".blif"))
        v = (ROOT / "block" / (n + "_lut6.v")).read_text()
        seen, err = set(), []
        for m in re.finditer(r"LUT(\d) #\(\.INIT\((\d+)'h([0-9a-f]+)\)\) \S+ \(\.O\(([^)]+)\), ([^;]*)\);", v):
            k, w, init, out = int(m.group(1)), int(m.group(2)), int(m.group(3), 16), m.group(4)
            pins = re.findall(r"\.I(\d)\(([^)]+)\)", m.group(5))
            src = [p for _, p in pins]
            if [int(q) for q, _ in pins] != list(range(k)) or w != 1 << k:
                err.append("pins " + out)
            elif out not in b or b[out][0] != src or b[out][1] != init:
                err.append("differs " + out)
            seen.add(out)
        luts = {o for o, (src, tt) in b.items() if not o.startswith("o[")}
        for i in range(32):
            src, tt = b["o[%d]" % i]
            m = re.search(r"assign o\[%d\] = ([^;]+);" % i, v)
            if not m or not ((src == [] and m.group(1) == "1'b0") or (len(src) == 1 and tt == 2 and m.group(1) == src[0])):
                err.append("output o[%d]" % i)
        if seen != luts:
            err.append("instances %d, BLIF LUTs %d" % (len(seen), len(luts)))
        bad += bool(err)
        print("%-18s LUT instances %3d  BLIF LUTs %3d  outputs 32  %s" % (n, len(seen), len(luts), "MATCH" if not err else "DIFFER " + "; ".join(err[:4])))
    raise SystemExit(1 if bad else 0)
