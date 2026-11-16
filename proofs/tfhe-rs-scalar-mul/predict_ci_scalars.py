"""Predicted PBS for the exact scalars naf_scalar_mul_count.rs draws (same splitmix64, same order).

Uses the plain-integer model in tfhe_scalar_mul_count.py, counting trivial PBS the way the
library's pbs-stats counter does, with the thread count of the runner (default 4).

Usage:  python -I -B predict_ci_scalars.py [samples] [seed] [threads]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tfhe_scalar_mul_count as model  # noqa: E402

M64 = (1 << 64) - 1


class SplitMix64:
    def __init__(self, seed):
        self.state = seed & M64

    def next(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & M64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
        return z ^ (z >> 31)


def main():
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261115
    model.THREADS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    model.COUNT_TRIVIAL = True
    rng = SplitMix64(seed)
    print(f"# prediction samples={samples} seed={seed} threads={model.THREADS} count_trivial=True")
    print("| width | case | scalar | unpatched PBS | patched PBS |")
    print("|---|---|---|---|---|")
    rows = []
    for width in (16, 32, 64):
        n = width // 2
        m = (1 << width) - 1
        edges = [("edge_zero", 0), ("edge_one", 1), ("edge_two", 2), ("edge_three", 3),
                 ("edge_all_ones", m), ("edge_pow2_odd_exponent", 1 << (width - 3)),
                 ("edge_pow2_even_exponent", 1 << (width - 2)), ("edge_0b1011", 0b1011),
                 ("edge_alternating", 0xAAAAAAAAAAAAAAAA & m), ("edge_top_run", m ^ (m >> 2))]
        randoms = [rng.next() & m for _ in range(samples)]
        for _ in range(len(edges) + samples):
            rng.next()  # the clear operand drawn per case
        for name, k in edges:
            u = model.library_scalar_mul(k, n)[0]
            p = model.patched_scalar_mul(k, n)[0]
            print(f"| {width} | {name} | {k} | {u} | {p} |")
        us = [model.library_scalar_mul(k, n)[0] for k in randoms]
        ps = [model.patched_scalar_mul(k, n)[0] for k in randoms]
        rows.append((width, len(randoms), sum(us) / len(us), max(us), sum(ps) / len(ps), max(ps)))
    print()
    print("| width | samples | unpatched mean | unpatched worst | patched mean | patched worst | mean change |")
    print("|---|---|---|---|---|---|---|")
    for width, cnt, um, uw, pm, pw in rows:
        print(f"| {width} | {cnt} | {um:.1f} | {uw} | {pm:.1f} | {pw} | {100 * (pm / um - 1):+.1f}% |")


if __name__ == "__main__":
    main()
