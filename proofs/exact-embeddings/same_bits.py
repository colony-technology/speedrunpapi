"""Run each engine with 1 and with 4 threads, in batches of 1 and of 32, and print the SHA-256 of the 2,758 vectors.

Each run is a fresh process, so the thread count is set before NumPy loads its BLAS: OPENBLAS_NUM_THREADS,
OMP_NUM_THREADS, MKL_NUM_THREADS and VECLIB_MAXIMUM_THREADS (Accelerate) all get the same value; onnxruntime gets
intra_op_num_threads. The exact engine must give one hash; the other two are reported as measured.

usage: python same_bits.py [exact float32 onnx]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
engines = [a for a in sys.argv[1:]] or ["exact", "float32", "onnx"]
seen = {}
for eng in engines:
    for threads in (1, 4):
        for batch in (1, 32):
            env = dict(os.environ)
            for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
                env[k] = str(threads)
            t0 = time.time()
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "exact_embed.py"), "hash", "--engine", eng,
                                "--batch", str(batch), "--threads", str(threads)],
                               env=env, capture_output=True, text=True)
            if r.returncode:
                print(r.stderr)
                sys.exit(r.returncode)
            h = r.stdout.split()[0]
            seen.setdefault(eng, set()).add(h)
            print("%-8s threads=%d batch=%-2d %s  (%.0f s)" % (eng, threads, batch, h, time.time() - t0), flush=True)
for eng, hs in seen.items():
    print("%-8s %d distinct hash%s over the four runs" % (eng, len(hs), "" if len(hs) == 1 else "es"))
sys.exit(0 if len(seen.get("exact", {""})) == 1 else 1)
