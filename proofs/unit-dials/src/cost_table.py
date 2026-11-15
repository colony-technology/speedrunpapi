#!/usr/bin/env python3
"""The cost tables from record/cost.txt (counts and levels as Yosys/ABC printed them).
Per set: range in bits, channel add and multiply (sum of LUT-6 over the channels, deepest channel), reading back,
binary adder and multiplier of the same width b, and LUT-6 per bit of range (log2 M).
usage: cost_table.py record/cost.txt
"""
import json
import re
import sys


def main():
    sets, cur = [], None
    for line in open(sys.argv[1]):
        line = line.strip()
        if line.startswith("{"):
            cur = {"spec": json.loads(line), "mods": {}}
            sets.append(cur)
        elif cur is not None and line.startswith("== negative"):
            cur = None
        elif cur is not None:
            m = re.match(r"(\w+): (\d+) LUT-6, (\d+) levels", line)
            if m:
                cur["mods"][m.group(1)] = (int(m.group(2)), int(m.group(3)))
    print("| set | unit | range bits | b | multiples of M compared | channel add LUT / levels | channel mul LUT / levels |"
          " reading back LUT / levels | binary add LUT / levels | binary mul LUT / levels |"
          " add LUT per bit, channels / binary | mul LUT per bit, channels / binary | back LUT per bit |")
    print("|" + " --- |" * 13)
    for s in sets:
        sp, md = s["spec"], s["mods"]
        ms = sp["moduli"]
        r = sp["log2M"]
        add = [md["chadd_%d" % m] for m in ms]
        mul = [md["chmul_%d" % m] for m in ms]
        al, ad = sum(a for a, _ in add), max(d for _, d in add)
        ml, mdp = sum(a for a, _ in mul), max(d for _, d in mul)
        bk, ba, bm = md["back"], md["binadd"], md["binmul"]
        print("| (%s) | %s | %.3f | %d | %d | %d / %d | %d / %d | %d / %d | %d / %d | %d / %d | %.2f / %.2f | %.2f / %.2f | %.2f |"
              % (", ".join(map(str, ms)), "yes" if sp["unit"] else "no", r, sp["b"], sp["multiples_compared"],
                 al, ad, ml, mdp, bk[0], bk[1], ba[0], ba[1], bm[0], bm[1],
                 al / r, ba[0] / r, ml / r, bm[0] / r, bk[0] / r))
    print()
    print("| set | channel | add LUT / levels | mul LUT / levels |")
    print("| --- | --- | --- | --- |")
    for s in sets:
        for m in s["spec"]["moduli"]:
            a, b = s["mods"]["chadd_%d" % m], s["mods"]["chmul_%d" % m]
            print("| (%s) | %d | %d / %d | %d / %d |" % (", ".join(map(str, s["spec"]["moduli"])), m, a[0], a[1], b[0], b[1]))


if __name__ == "__main__":
    main()
