#!/usr/bin/env python3
"""Stage 1 table from logs/summary.txt (lines written by harness.cpp). Prints Markdown."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/summary.txt"
main = {}
both = {}
for line in open(path):
    m = re.match(r"w=(\d+) p=(\d+) applied (\d+) \(finite nonzero (\d+), special (\d+)\) skipped_invalid_sig (\d+) "
                 r"mismatches (\d+) \(special (\d+), value (\d+), flags (\d+)\)", line)
    if m:
        main[(int(m.group(1)), int(m.group(2)))] = [int(x) for x in m.groups()[2:]]
    m = re.match(r"w=(\d+) p=(\d+) invalidExc&infiniteExc applied (\d+) value_wrong (\d+) flags_11000 (\d+)", line)
    if m:
        both[(int(m.group(1)), int(m.group(2)))] = [int(x) for x in m.groups()[2:]]
print("| w | p | documented | inputs applied | finite nonzero | special | mismatches (value, flags) |")
print("| --- | --- | --- | --- | --- | --- | --- |")
tot = {True: [0, 0, 0, 0], False: [0, 0, 0, 0]}
for (w, p), v in sorted(main.items()):
    doc = p <= 2 ** (w - 2) + 3
    print("| %d | %d | %s | %s | %s | %s | %s (%s, %s) |" % (w, p, "yes" if doc else "no", f"{v[0]:,}", f"{v[1]:,}",
                                                       f"{v[2]:,}", f"{v[4]:,}", f"{v[6]:,}", f"{v[7]:,}"))
    t = tot[doc]
    t[0] += v[0]; t[1] += v[1]; t[2] += v[2]; t[3] += v[4]
for doc in (True, False):
    t = tot[doc]
    print("\n%s formats: inputs %s, finite nonzero %s, special %s, mismatches %s" %
          ("documented" if doc else "undocumented", f"{t[0]:,}", f"{t[1]:,}", f"{t[2]:,}", f"{t[3]:,}"))
b = [sum(x[i] for x in both.values()) for i in range(3)]
print("\ninvalidExc = infiniteExc = 1 (included in special above): %s inputs, value not the NaN %s, flags 11000 %s"
      % (f"{b[0]:,}", f"{b[1]:,}", f"{b[2]:,}"))
