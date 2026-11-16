"""exact_mod against Python integers on random inputs of every shape the checker uses (light: a few seconds)."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("check", Path(__file__).with_name("check.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
rng = np.random.default_rng(5)
n_ok = 0
for rows, n, bits in ((8, 576, 17), (8, 1536, 30), (3, 49152, 53), (9, 64, 45), (20, 37, 53), (1, 49152, 17), (576, 1536, 17)):
    A = rng.integers(-(1 << (bits - 1)), 1 << (bits - 1), size=(rows, n), dtype=np.int64)
    A[0, 0] = (1 << bits) - 1 if bits < 63 else A[0, 0]                     # the extreme magnitude
    A[-1, -1] = -((1 << bits) - 1)
    vs = [rng.integers(0, p, size=n, dtype=np.int64) for p in C.PRIMES for _ in range(2)]
    ps = [p for p in C.PRIMES for _ in range(2)]
    got = C.exact_mod(A, vs, ps)
    for v, p, g in zip(vs, ps, got):
        Al, vl = A.tolist(), v.tolist()
        want = [sum(x * y for x, y in zip(row, vl)) % p for row in Al[:4]] + [sum(x * y for x, y in zip(Al[-1], vl)) % p]
        assert g[:4].tolist() + [int(g[-1])] == want, (rows, n, bits)
        n_ok += 1
print("exact_mod: %d of %d (shape, prime, vector) cases equal to Python integers" % (n_ok, n_ok))
