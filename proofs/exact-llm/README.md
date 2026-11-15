# Exact LLM: SmolLM2-135M

`HuggingFaceTB/SmolLM2-135M` (Apache-2.0), revision `93efa2f`, in integer arithmetic. 64 prompts. SHA-256 of the logits at every prompt position (471 positions × 49,152, int32 at 2^-16) and of the 64 greedy continuations of 48 tokens.

| machine | exact logits | float32 logits | onnxruntime logits | continuations, all three engines |
| --- | --- | --- | --- | --- |
| Linux, x86-64 | `30ed613b…cee773` | `e1f142df…2b018f` | `b0fd10d5…90e05b` | `a800ebad…7613cc` |
| Linux, aarch64 | `30ed613b…cee773` | `b2f3e029…f99637` | `bd9dd159…fb6374` | `a800ebad…7613cc` |
| macOS 26.7, ARM64 | `30ed613b…cee773` | `32b192d5…fa2db1` | `bd9dd159…fb6374` | `a800ebad…7613cc` |
| macOS 15.7, x86-64 | `30ed613b…cee773` | `83ccea5a…40be9c` | `761b6fb2…7e5d89` | `a800ebad…7613cc` |
| Windows Server 2025, x86-64 | `30ed613b…cee773` | `da18301e…71040d` | `b0fd10d5…90e05b` | `a800ebad…7613cc` |
| Windows 11, ARM64 | `30ed613b…cee773` | `b2f3e029…f99637` | `bd9dd159…fb6374` | `a800ebad…7613cc` |
| Apple M1, macOS 27.2 | `30ed613b…cee773` | `aafc4308…f738c2` | `bd9dd159…fb6374` | `a800ebad…7613cc` |
| distinct, 7 machines | 1 | 6 | 3 | 1 |

```sh
pip install numpy onnxruntime
python exact_llm.py check        # exit 1 if the exact pair differs from expected.sha256
```

Rows 1 to 6: GitHub Actions run [43671156245](https://github.com/lmtlssss/speedrunpapi/actions/runs/43671156245) (`.github/workflows/exact-llm.yml`, Python 3.12, NumPy 2.5.4). Row 7: Apple M1, Python 3.11.18, NumPy 2.4.6 with Accelerate, onnxruntime 1.32.0. Full hashes and every printed line: `record/machines.txt`. Batch 8, 0 values clamped on every machine.

## Distance to float32

| | exact | onnxruntime |
| --- | --- | --- |
| prompt positions with the same top-1 token as float32 | 471 of 471 | 471 of 471 |
| largest \|logit − float32 logit\|, Apple M1 | 0.0215 | 0.0006 |
| mean \|logit − float32 logit\|, Apple M1 | 0.0012 | 0.00002 |
| largest and mean, the six runners | 0.0215 to 0.0217, 0.0012 | |
| continuations, 64 × 48 tokens, equal to float32 | 64 of 64 | 64 of 64 |
| text, 8,176 tokens: same top-1 token as float32 | 8,160 (99.80 %) | 8,176 (100 %) |
| perplexity, float32 30.5718; Apple M1, float64 exp and log of the logits, not hashed | 30.5799 | 30.5717 |
| 256-token continuations, 64 prompts, batch 8, equal to float32 (16,384 tokens) | 64 of 64 | 64 of 64 |

Text: Tiny Shakespeare (`karpathy/char-rnn` at `370cbcd`), the first 8,192 tokens as 16 windows of 512. `distance.py`, `record/machines.txt`.

## Apple M1: threads and batch

| | 1 thread, batch 1 | 1 thread, batch 8 | 4 threads, batch 1 | 4 threads, batch 8 |
| --- | --- | --- | --- | --- |
| exact logits | `30ed613b…cee773` | `30ed613b…cee773` | `30ed613b…cee773` | `30ed613b…cee773` |
| float32 logits | `883b972a…bb89be` | `aafc4308…f738c2` | `883b972a…bb89be` | `aafc4308…f738c2` |
| onnxruntime logits | `bd9dd159…fb6374` | `bd9dd159…fb6374` | `bd9dd159…fb6374` | `bd9dd159…fb6374` |
| continuations, all three | `a800ebad…7613cc` | `a800ebad…7613cc` | `a800ebad…7613cc` | `a800ebad…7613cc` |
| 256-token continuations, 64 prompts: float32 batch 1 = batch 8; onnxruntime batch 1 = batch 8; both = exact | 64 of 64 | | | |

`same_bits.py`, `long_run.py`.

## Speed and memory, Apple M1

| | prefill, tokens/s | decode batch 8, tokens/s | decode batch 1, tokens/s | peak resident |
| --- | --- | --- | --- | --- |
| exact, one float64 matrix at a time (default) | 236 | 79.7 | 11.8 | 1,088 MB |
| exact, float64 matrices kept (`--keep`) | 224 | 92.2 | 14.5 | 1,775 MB |
| float32 | 1,037 | 130.1 | 55.2 | 1,116 MB |

`speed.py`. The 64-prompt hash run at batch 8: exact 61.7 s at 831 MB (default), 38.9 s at 1.82 GB (`--keep`); float32 28.3 s; onnxruntime 22.6 s. The 256-token run of the 64 prompts, exact, batch 8: 345 s at 1,496 MB.

## Method, in the order `exact_llm.py` computes

| | |
| --- | --- |
| weights | `round(w · 2^16)` of each bfloat16 value, ties to even; 0.69 % need the rounding. int32 `.npy`, memory-mapped; `int_weights` |
| scales | activations and norm weights 2^-16; weights 2^-16; rotary cos and sin 2^-20; exp table 2^-24; logits 2^-16, int32 |
| `round(v / 2^k)` | `(v + 2^(k−1)) >> k`; `rshift_round` |
| floor division | asserts `q·d ≤ n < (q+1)·d` on every call; `fdiv` |
| `isqrt(n)`, `n < 2^62` | float64 `sqrt`, then integer steps; asserts `s² ≤ n < (s+1)²` on every call; `isqrt` |
| embedding | `E[ids]` |
| RMS norm, per token (576) | `s = max(0, bitlength(max \|x\|) − 26)`; `ms = floor(Σ (x >> s)² / 576)`; `r = isqrt(ms + round(10^-5 · 2^(32−2s)))`; `y = floor(x · 2^(16−s) / r)`, asserted `\|y\| ≤ 25·2^16`; `round(y · g / 2^16)`; `rms` |
| linear | `round(clamp(x) · W / 2^16)`, `W` [in, out] float64 from int32; the down product in 6 chunks of 256 inputs, each in float64, summed in int64; `linear` |
| rotary, `i < 32` | `x'_i = round((x_i·C[p,i] − x_{i+32}·S[p,i]) / 2^20)`; `x'_{i+32} = round((x_{i+32}·C[p,i] + x_i·S[p,i]) / 2^20)`; `rope` |
| scores | `s = clamp(q) · clamp(k)` at 2^-32; query head `h` reads key-value head `floor(h/3)` |
| softmax | `m = max s` over the keys the row may read; `t = floor((m − s) / 2^19)` (1/√64 = 2^-3); `e = Exp(t)`, 0 for other keys; `p = floor(e · 2^16 / Σ e)`; `attention` |
| `Exp(t)` | `k = t >> 8`, `r = t mod 256`; `floor((E[k]·(256 − r) + E[k+1]·r) / 256)`, `k ≤ 6144` |
| context | `round(p · clamp(v) / 2^16)` |
| feed-forward | `round(SiLU(clamp(gate)) · clamp(up) / 2^16)`, then the down product |
| `SiLU(x)` | the same interpolation on `S`, for `−16 ≤ x < 16`; 0 below, `x` above |
| logits | `round(clamp(h) · E^T / 2^16)`, tied embedding, int32; `logits` |
| greedy | the first index of the largest integer logit |
| tokenizer | byte-level BPE from `tokenizer.json`: digits split singly; the GPT-2 pattern with `unicodedata` categories; 48,900 merges by rank; no BOS; `Tokenizer` |

| table, `make_tables.py` | definition | entries |
| --- | --- | --- |
| `tables/exp.txt` | `E[k] = round(2^24 · exp(−k/256))` | 6,145 |
| `tables/silu.txt` | `S[k] = round(2^16 · x / (1 + exp(−x)))`, `x = −16 + k/256` | 8,193 |
| `tables/cos.txt`, `tables/sin.txt` | `round(2^20 · cos(p · 100000^(−i/32)))`, its sine; `p < 512`, `i < 32` | 16,384 each |

Each table value is computed with mpmath at 60 and at 100 digits. Both round to the same integer, and none lies within 10^-30 of a half.

## Bound, `bounds.py`, `bounds.json`

The matrix product is float64 sums of products of integer entries, in any order, with or without fused multiply-add, on any number of threads. It is exact when the sum of \|terms\| ≤ 2^53, that is, when clamp × the largest Σ\|w\| over one output's inputs is at most 2^53.

| product | input clamp (real) | inputs per product | largest Σ\|w\| (integer) | bound |
| --- | --- | --- | --- | --- |
| q_proj, k_proj, v_proj | 2^12 | 576 | 27,338,729 | 2^52.704 |
| o_proj | 2^12 | 576 | 30,420,307 | 2^52.859 |
| gate_proj | 2^11 | 576 | 28,063,545 | 2^51.742 |
| up_proj | 2^11 | 576 | 64,996,192 | 2^52.954 |
| down_proj | 2^13 | 256 (6 chunks) | 9,976,648 | 2^52.250 |
| logits, tied embedding | 2^14 | 576 | 7,799,976 | 2^52.895 |
| scores q·k | q, k 2^7 | 64 | | 2^52 |
| context p·v | v 2^12 | Σp ≤ 2^16 | | 2^44 |

14 element-wise int64 operations, each below 2^63 (`isqrt` inputs below 2^62): `bounds.json`.

| clamp site | clamp (real) | peak, exact, 64 prompts | peak, float32, prompts and 8,192 text positions | clamp / peak |
| --- | --- | --- | --- | --- |
| residual stream | 2^16 | 19,508.7 | 20,294.3 (layer 12) | 3.2 |
| down input | 2^13 | 2,630.7 | 2,645.7 (layer 28) | 3.1 |
| up | 2^12 | 72.0 | 74.1 | 55 |
| logits input | 2^14 | 53.6 | 54.8 | 299 |
| gate | 2^12 | 50.7 | 50.7 | 81 |
| mlp input | 2^11 | 28.7 | 29.6 | 69 |
| k | 2^7 | 22.9 | 23.0 | 5.6 |
| q | 2^7 | 22.1 | 22.1 | 5.8 |
| v | 2^12 | 13.0 | 19.8 | 207 |
| attention input | 2^12 | 11.4 | 11.6 | 352 |
| o input | 2^12 | 9.5 | 10.9 | 375 |
| values clamped | | 0 on every run | | |

## Pins, `pins.json`

| file | source | SHA-256 |
| --- | --- | --- |
| `model.safetensors`, `tokenizer.json`, `config.json` | `HuggingFaceTB/SmolLM2-135M` @ `93efa2f097d58c2a74874c7e644dbc9b0cee75a2` | `80521b40…`, `9ca9acdd…`, `1d556eab…` |
| `onnx/model.onnx`, `onnx/model.onnx_data` | `onnx-community/SmolLM2-135M-ONNX` @ `d0ae6834f1df45e0e95b5fdae95e536f9ca7cd3f` | `de4f7dbe…`, `3ffe0420…` |
| prompts: `sentence1` of the first 64 lines of `test.jsonl.gz` | `mteb/stsbenchmark-sts` @ `96943a16ea6a35129e253c659081cb59daf81b30` | `524a7513…` |
| text: `data/tinyshakespeare/input.txt` | `karpathy/char-rnn` @ `370cbcd448eb7daf32f21a6be560b70e0b33c4e3` | `86c4e6aa…` |

## Checks

| check | result | command |
| --- | --- | --- |
| tokenizer against `tokenizers` 0.23.3: 64 prompts, 2,000 text lines, the 2,000 lines as one string | 0 differences, 33,097 tokens | `compare_tokenizer.py` |
| tables against their generator | equal | `make_tables.py --check` |
| products below 2^53, int64 below 2^63 | holds | `bounds.py` |
| float32 against onnxruntime | top-1 equal at all 471 prompt and 8,176 text positions; largest logit difference 0.0006 | `distance.py DIR float32 onnx` |
| notebook, its cells run as one script in a fresh directory with an empty cache, Apple M1 | downloads checked; exact MATCH (63 s); top-1 471 of 471; continuations 64 of 64 | `exact_llm.ipynb`, `make_notebook.py --check` |

## Prior work

| work | page | stated there |
| --- | --- | --- |
| FFLAS-FFPACK | [arXiv cs/0601133](https://arxiv.org/abs/cs/0601133), ACM TOMS 2009 | exact matrix products over finite fields with floating-point BLAS while λ(p−1)² < 2^53 |
| I-BERT | [arXiv 2101.01321](https://arxiv.org/abs/2101.01321) | BERT inference "with integer-only arithmetic", integer GELU, softmax and LayerNorm, GLUE accuracy similar to full precision |
| I-LLM | [arXiv 2405.17849](https://arxiv.org/abs/2405.17849) | integer-only LLM inference at W4A4, bit-shift softmax, exp and normalisation |
| Gensyn RepOps | [gensyn.ai/ree](https://gensyn.ai/ree), [docs](https://docs.gensyn.ai/tech/ree/advanced-usage/internals.md) | bitwise-identical floating point across supported hardware: fixed reduction order, FP32 fused multiply-add, correctly rounded transcendentals |
| ARC engine | [arXiv 2603.24904](https://arxiv.org/abs/2603.24904) | integer-only inference (INT8 weights, Q16 activations), identical hashes across ARM and x86 (and GPU, in the paper's body); WikiText-2 perplexity 144 for Llama-2-7B-Chat on the engine against 5.47 for Llama-2-7B base in FP16 (Table 5) |

## Files

| file | |
| --- | --- |
| `exact_llm.py` | pins and downloads, safetensors parser, tokenizer, float32 and onnxruntime baselines, the exact model, `hash`, `text`, `check` |
| `bounds.py`, `bounds.json` | the bound |
| `make_tables.py`, `tables/` | the four tables |
| `same_bits.py` | 1 and 4 threads × batch 1 and 8 |
| `long_run.py` | 256-token continuations |
| `distance.py` | exact against float32 |
| `speed.py` | tokens/s and peak memory |
| `compare_tokenizer.py` | the tokenizer against `tokenizers` |
| `exact_llm.ipynb`, `make_notebook.py` | the notebook, NumPy only |
| `pins.json`, `expected.sha256` | pins; the two exact hashes |
| `record/machines.txt` | every line of the seven machines |

## Your model

One model of yours, up to 500 million parameters, made exact this way: 1,800 USD, fixed.

You send the model's name and revision, the inputs you care about and the machines it must agree on. You receive the code, the hashes, and the comparison against float32 as in the tables above.
Full refund if two of your machines print different hashes.

Pay: https://buy.stripe.com/4gM8wO3Ho0c7dUubo76c007 · Questions: lmtlssss@colony.technology

Larger work, by contract: the same address.
