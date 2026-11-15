# Exact embeddings

`sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0) computed in integer arithmetic, so that the same sentence gives the same bits on every machine: 384 integers of 16 bits per sentence, scale 2^-15. Beside it are two float baselines of the same model, a plain float32 pass in NumPy and `onnxruntime` on the model's own `onnx/model.onnx`.

On the 2,758 sentences of the STS-B test set:
- The exact model gives one SHA-256 on seven machines: Linux, Windows and macOS, x86-64 and ARM64.
- On the same seven machines the float32 baseline gives six different hashes, and so does onnxruntime.
- On one of them, an Apple M1, the exact hash is also the same with 1 or 4 BLAS threads and in batches of 1 or 32, where both float baselines change with the batch size.
- STS-B Spearman is 0.8203 for all three engines on every machine. Every exact vector has cosine at least 0.9999997 with its float32 vector.

`exact_embeddings.ipynb` does the same in Colab with NumPy alone.

## Method

The model is read from its own files at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (`pins.json`): BERT, 6 layers, hidden 384, 12 heads of 32, intermediate 1536, GELU, LayerNorm with eps 1e-12; then mean pooling over the attention mask and L2 normalisation (`modules.json`, `1_Pooling/config.json`); at most 256 tokens. `model.safetensors` is parsed here: an 8-byte length, a JSON header, raw little-endian float32. Nothing is unpickled.

Every tensor is an integer array with a power-of-two scale:

| | fraction bits | in code |
| --- | --- | --- |
| activations | 16 | `A` |
| weights | 16 | `WB` |
| biases | 32 | `A + WB` |
| LayerNorm gain and shift, embeddings | 16 | |
| output | 15, int16 | `OUT` |

Weights are rounded once from the published float32 values: `w_int = round(w * 2^16)`, to nearest, ties to even. The scaling by a power of two is exact, so this is exact arithmetic plus one rounding, the same on every machine; the integer model is not stored. `1/sqrt(32)` is folded into the query weights and bias before rounding: `round(w * 2^16 / sqrt 32) = round(w * 2^13 * sqrt 2)`, computed exactly in Python integers as `floor((isqrt(8 p^2 // q^2) + 1) / 2)` for `w * 2^13 = p / q`.

Matrix products are the only floating-point operation: the machine's float64 BLAS on integer-valued arrays. Before each product every activation is clamped to `[-2^7, 2^7]` (`C = 2^23` integer units). Then every term and every partial sum is an integer of magnitude at most `C * sum |w|`, below 2^53 (`bounds.py`, `bounds.json`), and float64 holds those exactly: the product is exact in any order, with or without fused multiply-add, on any number of threads.

Element-wise work is NumPy int64. `round(v / 2^k)` is `(v + 2^(k-1)) >> k`. `floor` is Python's floor division. `isqrt(n)` is float64 `sqrt`, then integer steps until `s^2 <= n < (s + 1)^2`, which is asserted on every call, as is `q d <= n < (q + 1) d` for every floor division. Each step, exactly as `exact_embed.py` computes it:

- Linear: `y = round((clamp(x, C) . W + b) / 2^16)`.
- LayerNorm, over the 384 values of a token: `x = clamp(x, 2^25)`; `mu = floor(sum x / 384)`; `d = x - mu`; `v = floor(sum d^2 / 384)`; `s = isqrt(v + 1)`; `y = floor(d * 2^16 / s)`; output `round(y * g / 2^16) + b`. The `+ 1` stands for eps: 1e-12 is below one unit (2^-32) of `v`, so eps is 2^-32.
- Attention, per head:
  - scores `s = clamp(q, C) . clamp(k, C)` at 2^-32, with `1/sqrt(32)` already in `q`;
  - `m` the largest score over the unmasked keys;
  - `t = floor((m - s) / 2^16)`;
  - `e = Exp(t)` at 2^-24, 0 for masked keys;
  - `p = floor(e * 2^16 / sum e)`;
  - context `round(p . clamp(v, C) / 2^16)`.
- `Exp(t)`: `k = floor(t / 2^8)`, `r = t mod 2^8`; `floor((E[k] (256 - r) + E[k + 1] r) / 256)`, with `k` and `k + 1` capped at 6144.
- `GELU(x)`: `u = x + 8 * 2^16`. For `0 <= u < 16 * 2^16`, `k = floor(u / 2^8)`, `r = u mod 2^8` and the result is `floor((G[k] (256 - r) + G[k + 1] r) / 256)`. Below that range the result is 0, above it `x`.
- Pooling and output:
  - `x = clamp(x, C)`; `m = floor(sum x / n)` over the `n` unmasked tokens;
  - `N = isqrt(sum m^2)`; output `clamp(floor(m * 2^15 / max(N, 1)), -2^15, 2^15 - 1)`.
- The cosine of two outputs is their integer dot product divided by 2^30.

The tables are `tables/exp.txt`, `E[k] = round(2^24 exp(-k / 256))`, k = 0 .. 6144, and `tables/gelu.txt`, `G[k] = round(2^16 x Phi(x))`, x = -8 + k / 256, k = 0 .. 4096. `make_tables.py` computes each value with mpmath at 60 and at 100 digits; both must round to the same integer, and the exact value must lie further than 10^-30 from a half-integer. No `exp`, `erf` or `tanh` is called at run time.

The tokenizer is BERT WordPiece, uncased with accents stripped, from `vocab.txt`, in plain Python (`Tokenizer` in `exact_embed.py`).

`jax_runner.py` executes the same integer semantics in JAX with `jax_enable_x64`: every product is an int64 `einsum`, the tables are gathers, the square root is digit by digit, and there is no floating point on that path. Its int64 headroom is in `bounds.json`.

## Results

The sentences are the STS-B test set from `mteb/stsbenchmark-sts` at revision `96943a16ea6a35129e253c659081cb59daf81b30`, file `test.jsonl.gz`, SHA-256 `524a7513…834e1c`: 1,379 pairs, taken as `sentence1`, `sentence2` for each line in order, 2,758 sentences. A hash is the SHA-256 of all 2,758 vectors, little-endian, int16 for the exact model and float32 for the baselines.

Seven machines, batch 32. Six are GitHub Actions run [43666680107](https://github.com/lmtlssss/speedrunpapi/actions/runs/43666680107) (`exact_embed.py check` on each runner, Python 3.12, NumPy 2.5.4); the seventh is an Apple M1 (Python 3.11.18, NumPy 2.4.6 with Accelerate, onnxruntime 1.32.0). The full hashes and every line the runners printed are in `record/machines.txt`.

| machine | exact | float32 (NumPy) | onnxruntime |
| --- | --- | --- | --- |
| Windows Server 2025, x86-64 | `031d6912…202934` | `dcd75ea1…8f70c8` | `d05672ac…50e30b` |
| Windows 11, ARM64 | `031d6912…202934` | `9d5e0207…847f69` | `7c5761c3…8a9dec` |
| macOS 26.7, ARM64 | `031d6912…202934` | `ff2b8c46…15c96b` | `dba00dea…724a5f` |
| Linux, x86-64 | `031d6912…202934` | `b945f729…12402d` | `0303c976…e6e27a` |
| Linux, aarch64 | `031d6912…202934` | `9d5e0207…847f69` | `cd932aa3…bbb6b8` |
| macOS 15.7, x86-64 | `031d6912…202934` | `debaf68a…3f5e1e` | `ae4ba479…282fe2` |
| Apple M1, macOS 27.2 | `031d6912…202934` | `82175022…5092c1` | `dba00dea…724a5f` |

The exact model gave one hash on all seven machines, and every runner printed MATCH and 0 clamped values. The float32 baseline gave six different hashes on the seven; only Windows 11 on ARM64 and Linux on aarch64 agreed. onnxruntime gave six different hashes on the seven; only the two Apple ARM64 machines agreed.

On the Apple M1, each engine with 1 and with 4 threads, in batches of 1 and of 32. BLAS threads were set through `VECLIB_MAXIMUM_THREADS` and the OpenBLAS, OpenMP and MKL variables; onnxruntime threads through `intra_op_num_threads` (`same_bits.py`).

| engine | 1 thread, batch 1 | 1 thread, batch 32 | 4 threads, batch 1 | 4 threads, batch 32 |
| --- | --- | --- | --- | --- |
| exact | `031d6912…202934` | `031d6912…202934` | `031d6912…202934` | `031d6912…202934` |
| float32 (NumPy) | `e360cbe2…9f3c1c` | `82175022…5092c1` | `e360cbe2…9f3c1c` | `82175022…5092c1` |
| onnxruntime | `c4db2632…b39c0d` | `dba00dea…724a5f` | `c4db2632…b39c0d` | `dba00dea…724a5f` |

`expected.sha256` holds the exact hash in full: `031d6912ba5a0824fd2b2562abb592fe5caf8053e0d5a2060cf051a9ab202934`. On the M1 the float hashes depend on the batch size, because padding changes the shapes the products are computed in, and not on the thread count.

`jax_runner.py` on the M1's CPU, every product an int64 einsum with no floating point anywhere, gave the same hash, `031d6912…202934`, in 738 s. The notebook's GPU cell runs the same code on a GPU; no GPU run is recorded here.

Accuracy, STS-B test, Spearman of the cosine against the gold scores: exact 0.8203 (0.820321), float32 0.8203 (0.820325). Cosine between the exact and the float32 vector of each sentence: minimum 0.9999997, mean 0.9999999. No value reached a clamp on these sentences. The largest magnitudes were 30.3 at an input of a product (clamp 128) and 224.4 at a LayerNorm input (clamp 512).

The float32 baseline against onnxruntime on the first 100 sentences: cosine 1.00000000 at the minimum, largest difference in any component 2.2e-7 (`validate_float.py`). The tokenizer against the `tokenizers` library (0.23.3, the model's `tokenizer.json`): 0 differences on all 2,758 sentences, the longest 46 tokens (`compare_tokenizer.py`).

Time for the 2,758 sentences on the M1, batch 32: exact 21 s, float32 12 s.

## Run

```sh
pip install numpy                       # the exact model and the float32 baseline
python exact_embed.py check             # downloads the pinned files, checks their SHA-256, prints three hashes,
                                        # MATCH or DIFFERENT, and the STS-B numbers; exit 1 if the exact hash differs
python exact_embed.py hash --engine exact --batch 1
python same_bits.py                     # each engine with 1 and 4 threads, batches of 1 and 32
python bounds.py                        # the certificate below; writes bounds.json
python make_tables.py --check           # the tables against their generator (needs mpmath)
python jax_runner.py --device cpu       # the JAX int64 executor (needs jax)
python compare_tokenizer.py             # needs tokenizers
python validate_float.py                # needs onnxruntime
python make_notebook.py --check         # the notebook carries the current files
```

Downloads go to `.cache/` in this folder, or to `$EXACT_EMBED_CACHE`. No model weights are in the repository.

`.github/workflows/exact-embeddings.yml` runs `exact_embed.py check` on `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest`, `macos-15-intel`, `windows-latest` and `windows-11-arm`, prints the three hashes and fails if the exact hash differs from `expected.sha256`. Trigger: `workflow_dispatch` and pushes that touch this folder.

## Proof

The claim is that the exact model's output depends only on the pinned files and the arithmetic written above, not on the machine, the BLAS, the thread count or the batch.

1. Element-wise operations are integer operations on int64 with stated rounding. `bounds.json` lists each with its largest possible magnitude, all below 2^63. The inputs of `isqrt` are below 2^62. Every `isqrt` and every floor division checks its result by its bracket on every call.
2. Matrix products are exact. `bounds.py` takes the integer weights the model uses and computes, for every one of the 36 weight matrices, the largest row sum of absolute values times the clamp `C = 2^23`. The largest is 2^46.586 (layer 5, `output.dense`). For the two products of activations, scores are at most `32 C^2 = 2^51` and context `2^16 C = 2^39`, because the probabilities of a row are floors of numbers that sum to 2^16. All are below 2^53, so float64 represents every term and every partial sum, and the order of summation cannot change the result.
3. Weights are a function of the published float32 values. `bounds.py` re-checks all 887,040 folded query values by the integer inequality `(2n - 1)^2 q^2 < 8 p^2 < (2n + 1)^2 q^2`.
4. The tables are a function of their definition. `make_tables.py --check` regenerates them at two precisions.
5. The tokenizer uses Python's `unicodedata`. Its output on these sentences equals the reference library's; other text may depend on the Unicode version of the Python that runs it.

What ran:
- The six GitHub runners of run 43666680107 and the Apple M1 gave the same exact hash. Between them they cover three operating systems, on x86-64 and on ARM64.
- On the M1 the hash was the same over 1 and 4 threads and batches of 1 and 32.
- The float baselines on the same machines gave six hashes each.
