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

## exact-16: every product operand a 16-bit integer

`Exact16` in `exact_llm.py`. Every operand of every matrix product is an integer within ±(2^15 − 1), each with its own power-of-two scale; the work between products is the exact model's. A product over n inputs is then exact on three routes, and the routes give the same bits. The bound depends on n alone, not on the weights or the clamps.

| route | the product | exact while | engine |
| --- | --- | --- | --- |
| f64 | one float64 product | n · (2^15 − 1)^2 < 2^53 | `exact16-f64` |
| f32 | `a = 256 a1 + a0`, `a0` in [−128, 127], `a1` in [−128, 128], the same for `b`; four float32 products in chunks of 1,024 inputs | partial sums ≤ 1,024 · 2^14 = 2^24 | `exact16-f32` |
| i8 | `a1 = a >> 8` int8, `a0 = a & 255` uint8; four int32 products, onnxruntime `MatMulInteger` (NumPy int32 where onnxruntime is missing, named `i8-numpy`) | n · 255^2 < 2^31, n ≤ 33,025 | `exact16-i8` |

`a · b = 2^16 G11 + 2^8 (G10 + G01) + G00`, `Gij = ai · bj`, added in int64; `mm16`. The f32 digits have at most 8 significant bits, so they are exact as TF32 and bfloat16 inputs too, with float32 accumulation (not run here). `MatMulInteger` is a one-node ONNX model (opset 13) written as protobuf bytes in `exact_llm.py`; onnxruntime 1.32.0 gives the int32 product for all four pairs of uint8 and int8.

| Apple M1, 64 prompts | logits | continuations | clamped |
| --- | --- | --- | --- |
| `exact16-f64`, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-f32`, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-i8`, onnxruntime 1.32.0, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-f64`, batch 1 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |

The continuations are the exact model's and float32's. `python exact_llm.py check` runs the three routes against `expected-16.sha256`; exit 1 if any route differs. Full hashes: `record/exact16-m1.txt`.

| exact-16, in the order `Exact16` computes | |
| --- | --- |
| weights | `w16 = rint(w · 2^g)` from the bfloat16 values, `g` per output row the largest with every entry within ±(2^15 − 1) (the tied embedding: one `g` per token); int16 `.npy`, memory-mapped; `int16_weights` |
| product inputs | per token vector: `sh = max(0, bitlength(max \|x\|) − 15)`, one more if the rounding reaches 2^15; `x16 = round(x / 2^sh)`; `block16` |
| peeled terms | 2 per product, per token vector: its two largest \|x\| (ties to the lower index) kept whole; each `x · w16` is an exact wide term added in int64 before the one rounding, on every route; `peel_index` |
| linear, logits | `y = round((2^sh · x16 · w16 + Σ peeled x · w16) / 2^g)`, one rounding; `product` |
| scores | `q16 · k16`, `q` and `k` block-shifted per head vector; `s = 2^(sh_q + sh_k) · q16 · k16` at 2^-32 |
| softmax | as the exact model, then `p = round(floor(e · 2^16 / Σ e) / 2)` at 2^-15, held at 2^15 − 1 (20,174 values over the 64 prompts at batch 1) |
| context | `v` whole, `v = 2^15 vh + vl`, `vl = v & (2^15 − 1)`, `\|vh\| ≤ 2^13` within the clamp; `round((2^15 · p16 · vh + p16 · vl) / 2^15)` at 2^-16. No shift, so no position reads another key's magnitude, a later token or the padding |
| everything else | the exact model's: norms, rotary, the exp and SiLU tables, the clamps |

| product, `bounds16.py` | inputs n | f64, below 2^53 | f32, chunk, at most 2^24 | i8, below 2^31 |
| --- | --- | --- | --- | --- |
| q, k, v, o, gate, up, logits | 576 | 2^39.170 | 576, 2^23.170 | 2^25.159 |
| down | 1,536 | 2^40.585 | 1,024, 2^24.000 | 2^26.574 |
| scores q·k | 64 | 2^36.000 | 64, 2^20.000 | 2^21.989 |
| context p·vh, p·vl | 512 keys at most | 2^39.000 | 512, 2^23.000 | 2^24.989 |

Weight row scales `g`: q 12..19, k 12..18, v 13..17, o 12..17, gate 11..16, up 12..16, down 12..16, embedding 14..16. 17 int64 operations around the products, largest 2^59.733 (rotary): `bounds-16.json`.

### The width, measured

Each row narrows the exact model's product operands and is compared with float32 (perplexity 30.57175); Apple M1, 0 values clamped in every row. Inputs: product inputs per token vector; weights: per output row from bfloat16; attention: q and k per head vector, p at 2^-15. In these rows `v` had one shift per key-value head over all keys; exact-16 takes `v` whole in two halves (last row). Peel k: the k largest \|x\| of each product input kept whole. The 14- and 12-bit rows are the edge.

| row | prompt top-1 | logit difference, largest / mean | continuations | text top-1 | perplexity |
| --- | --- | --- | --- | --- | --- |
| exact model | 471/471 | 0.0215 / 0.0012 | 64/64 | 8,160/8,176 | 30.5799 |
| inputs 16 (attention 16) | 471/471 | 1.023 / 0.0210 | 63/64 | 8,169/8,176 | 30.5720 |
| weights 16 | 471/471 | 0.053 / 0.0029 | 64/64 | 8,159/8,176 | 30.5800 |
| both 16 | 471/471 | 1.137 / 0.0223 | 63/64 | 8,167/8,176 | 30.5717 |
| both 16, peel 1 | 471/471 | 0.175 / 0.0078 | 63/64 | 8,171/8,176 | 30.5711 |
| both 16, peel 2 (chosen) | 471/471 | 0.058 / 0.0026 | 63/64 | 8,173/8,176 | 30.5714 |
| both 16, peel 4 | 471/471 | 0.059 / 0.0030 | 64/64 | 8,173/8,176 | 30.5713 |
| inputs 16, peel 1 / 2 / 4 | 471 / 471 / 471 | 0.156 / 0.034 / 0.031 largest | 63 / 64 / 64 | 8,171 / 8,172 / 8,172 | 30.5713 / 30.5717 / 30.5716 |
| inputs 14 / 12 (attention 14 / 12) | 408 / 404 | 3.01 / 7.17 largest | 63 / 60 | 8,128 / 8,025 | 30.5820 / 30.6460 |
| weights 14 / 12 | 471 / 469 | 0.247 / 0.997 largest | 64 / 62 | 8,161 / 8,143 | 30.5795 / 30.5820 |
| both 14 / both 14, peel 2 / both 12 | 411 / 470 / 402 | 3.13 / 0.288 / 7.04 largest | 64 / 63 / 59 | 8,132 / 8,158 / 8,044 | 30.5800 / 30.5723 / 30.6415 |
| exact-16: both 16, peel 2, `v` in two halves | 471/471 | 0.0592 / 0.0027 | 64/64 | 8,171/8,176 | 30.5715 |

The large difference at 16-bit inputs is one outlier per vector setting its shift: peel 1 brings it to 0.175, peel 2 to 0.03 to 0.06, peel 4 adds nothing; peel 2 also takes 14-bit inputs and weights from 411 to 470. `measure16.py` (rows 1 to 11, against saved float32 runs), `record/exact16-table.txt`; last row `exact_llm.py hash`, `text` and `distance.py`.

## Distance to float32

| | exact | exact-16 | onnxruntime |
| --- | --- | --- | --- |
| prompt positions with the same top-1 token as float32 | 471 of 471 | 471 of 471 | 471 of 471 |
| largest \|logit − float32 logit\|, Apple M1 | 0.0215 | 0.0592 | 0.0006 |
| mean \|logit − float32 logit\|, Apple M1 | 0.0012 | 0.0027 | 0.00002 |
| largest and mean, the six runners | 0.0215 to 0.0217, 0.0012 | | |
| continuations, 64 × 48 tokens, equal to float32 | 64 of 64 | 64 of 64 | 64 of 64 |
| text, 8,176 tokens: same top-1 token as float32 | 8,160 (99.80 %) | 8,171 (99.94 %) | 8,176 (100 %) |
| perplexity, float32 30.5718; Apple M1, float64 exp and log of the logits, not hashed | 30.5799 | 30.5715 | 30.5717 |
| 256-token continuations, 64 prompts, batch 8, equal to float32 (16,384 tokens) | 64 of 64 | not run | 64 of 64 |

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
| exact-16: every product within its route's bound, int64 below 2^63 | holds | `bounds16.py` |
| exact-16 routes against int64 products: 7 shapes (2-D and the batched attention shapes, widths 1,023 to 1,536 across the f32 chunk edge) × 5 operand kinds (random, all ±(2^15 − 1), p-like), int64 and int16 right operands | 0 different on all three routes; the int16 digit split equals the int64 one for all 65,535 values; peel ties to the lower index | `routes_test.py` |
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
| `exact_llm.py` | pins and downloads, safetensors parser, tokenizer, float32 and onnxruntime baselines, the exact model, exact-16 on its three routes, `hash`, `text`, `check` |
| `bounds.py`, `bounds.json` | the bound |
| `bounds16.py`, `bounds-16.json` | the exact-16 bound, per route |
| `routes_test.py` | the three routes against int64 products |
| `measure16.py`, `record/exact16-table.txt` | the width table, one row per run |
| `expected-16.sha256`, `record/exact16-m1.txt` | the two exact-16 hashes; every exact-16 line of the M1 |
| `make_tables.py`, `tables/` | the four tables |
| `same_bits.py` | 1 and 4 threads × batch 1 and 8, any engine |
| `long_run.py` | 256-token continuations |
| `distance.py` | exact against float32 |
| `speed.py` | tokens/s and peak memory |
| `compare_tokenizer.py` | the tokenizer against `tokenizers` |
| `exact_llm.ipynb`, `make_notebook.py` | the notebook, NumPy only |
| `pins.json`, `expected.sha256` | pins; the two exact hashes |
| `record/machines.txt` | every line of the seven machines |
