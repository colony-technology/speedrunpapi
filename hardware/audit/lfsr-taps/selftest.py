"""Self-test of the number theory and GF(2) routines of audit_taps.py on known answers.
usage: python3 selftest.py   (from this folder)"""
import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
import tempfile
sys.argv = [sys.argv[0], os.path.join(here, "data"), tempfile.mkdtemp()]
spec = importlib.util.spec_from_file_location("audit_taps", os.path.join(here, "audit_taps.py"))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

primes = [2, 3, 5, 7, 97, 7919, (1 << 61) - 1, (1 << 89) - 1, (1 << 127) - 1, 2 ** 255 - 19, 274177, 67280421310721]
composites = [1, 4, 9, 561, 1105, 2047, 3215031751, 3825123056546413051, (1 << 64) + 1, (1 << 128) + 1, 25326001,
              (2 ** 89 - 1) * (2 ** 61 - 1), 3 * 3 * 7]
bad = [p for p in primes if not t.probable_prime(p)] + [c for c in composites if t.probable_prime(c)]
print("primality: %d primes, %d composites (including strong base-2 pseudoprimes 2047, 3215031751), wrong %s"
      % (len(primes), len(composites), bad))
# GF(2): x^2+x+1 primitive; x^4+x^3+x^2+x+1 irreducible not primitive (order 5); x^4+1 reducible; x^8+x^4+x^3+x^2+1 primitive
cases = [(0b111, 2, "primitive"), (0b11111, 4, "irreducible, not primitive"), (0b10001, 4, "reducible"),
         (0b100011101, 8, "primitive"), (0b100011011, 8, "irreducible, not primitive")]
for P, n, want in cases:
    got = t._primitive(P, n)[0]
    print("  %s degree %d: %s %s" % (bin(P), n, got, "ok" if got == want else "WRONG, want " + want))
# factorisation checks
for n in (64, 127, 786, 1024, 2048, 4096):
    f = t.factors_of(n)
    print("  2^%d - 1: %s" % (n, "%d distinct primes, verified, from %s" % (len(f["primes"]), f["source"]) if f else "no verified factorisation"))
