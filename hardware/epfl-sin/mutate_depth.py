"""usage: python -I mutate_depth.py NET.blif OUTDIR [COUNT] [SEED] [LEVELS]
Writes COUNT mutants of NET.blif (default 12): each flips one truth-table bit of one LUT. The LUTs are spread over
the levels (level = longest path from an input, read from the file); the flipped pattern is random. Each mutant's
LUT is rewritten as the minterms of its new on-set. Prints one line per mutant: file, node, level, fanins, pattern.
"""
import os
import random
import sys


def blocks(lines):
    """-> list of (start, end, output, fanins) of the .names blocks; continuation lines joined."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(".names"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("."):
                j += 1
            t = ln.split()
            out.append((i, j, t[-1], t[1:-1]))
            i = j
        else:
            i += 1
    return out


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    rnd = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 2027)
    text = open(src).read().replace("\\\n", " ")
    lines = text.split("\n")
    bl = blocks(lines)
    level = {}
    pending = bl
    while pending:
        rest = []
        for b in pending:
            if all(x in level or x.startswith("a[") for x in b[3]):
                level[b[2]] = 1 + max([level.get(x, 0) for x in b[3]], default=0)
            else:
                rest.append(b)
        assert len(rest) < len(pending)
        pending = rest
    by = {}
    for b in bl:
        by.setdefault(level[b[2]], []).append(b)
    levs = sorted(by)
    if len(sys.argv) > 5:                      # optional comma list of levels, one mutant each
        levs = [int(x) for x in sys.argv[5].split(",")]
    pick = [levs[i % len(levs)] for i in range(count)]
    os.makedirs(outdir, exist_ok=True)
    for m, lev in enumerate(pick):
        b = rnd.choice(by[lev])
        while len(b[3]) == 0:
            b = rnd.choice(by[lev])
        start, end, name, fan = b
        k = len(fan)
        on = set()
        pol = "1"
        for row in lines[start + 1:end]:
            t = row.split()
            if not t:
                continue
            cube, pol = t[0], t[1]
            for r in range(1 << k):
                if all(c == "-" or int(c) == (r >> i) & 1 for i, c in enumerate(cube)):
                    on.add(r)
        if pol == "0":
            on = set(range(1 << k)) - on
        r = rnd.randrange(1 << k)
        on ^= {r}
        new = [".names %s %s" % (" ".join(fan), name)]
        new += ["".join(str((p >> i) & 1) for i in range(k)) + " 1" for p in sorted(on)]
        path = os.path.join(outdir, "mutant_%02d.blif" % m)
        with open(path, "w") as f:
            f.write("\n".join(lines[:start] + new + lines[end:]))
        print("%s  node %s  level %d  fanins %d  pattern %d" % (path, name, lev, k, r), flush=True)


if __name__ == "__main__":
    main()
