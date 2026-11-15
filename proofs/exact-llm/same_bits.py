"""Run each engine with 1 and with 4 threads, in batches of 1 and of 8, and print its two SHA-256: over the logits of
every prompt position, and over the 64 greedy continuations of 48 tokens.

Each run is a fresh process, so the thread count is set before NumPy loads its BLAS: OPENBLAS_NUM_THREADS,
OMP_NUM_THREADS, MKL_NUM_THREADS and VECLIB_MAXIMUM_THREADS (Accelerate) all get the same value; onnxruntime gets
intra_op_num_threads. Each exact engine (exact, exact16-ROUTE) must give one pair of hashes; the others are reported as measured.

usage: python same_bits.py [exact exact16-f64 exact16-f32 exact16-i8 float32 onnx]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
engines = sys.argv[1:] or ["exact", "float32", "onnx"]
seen = {}
for eng in engines:
    for threads in (1, 4):
        for batch in (1, 8):
            env = dict(os.environ)
            for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
                env[k] = str(threads)
            t0 = time.time()
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "exact_llm.py"), "hash", "--engine", eng,
                                "--batch", str(batch), "--threads", str(threads)], env=env, capture_output=True, text=True)
            if r.returncode:
                print(r.stderr)
                sys.exit(r.returncode)
            hl, hc = r.stdout.split()[:2]
            seen.setdefault(eng, set()).add((hl, hc))
            print("%-11s threads=%d batch=%d logits %s continuations %s (%.0f s)"
                  % (eng, threads, batch, hl, hc, time.time() - t0), flush=True)
for eng, hs in seen.items():
    print("%-11s %d distinct pair%s over the four runs" % (eng, len(hs), "" if len(hs) == 1 else "s"))
sys.exit(0 if all(len(hs) == 1 for e, hs in seen.items() if e.startswith("exact")) else 1)
