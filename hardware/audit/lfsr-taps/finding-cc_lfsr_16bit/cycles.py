"""Every cycle of the 16-bit register, over all 65,536 states, under the rule of cc_lfsr_16bit.sv:
shift_in = !(q[a] ^ q[b] ^ q[c] ^ q[d]);  q' = {q[14:0], shift_in}.  As shipped: taps 15, 12, 5, 1. Fixed: 15, 14, 12, 3.
usage: python3 -I cycles.py"""


def cycles(taps):
    seen = bytearray(1 << 16)
    out = []
    for s in range(1 << 16):
        if seen[s]:
            continue
        n, q = 0, s
        while not seen[q]:
            seen[q] = 1
            b = 1
            for t in taps:
                b ^= (q >> t) & 1
            q = ((q << 1) & 0xFFFF) | b
            n += 1
        out.append(n)
    return sorted(out, reverse=True)


for name, taps in (("as shipped, taps 15, 12, 5, 1", (15, 12, 5, 1)), ("fixed, taps 15, 14, 12, 3", (15, 14, 12, 3))):
    c = cycles(taps)
    print("%s: %d cycles, lengths %s, total %d" % (name, len(c), c, sum(c)))
