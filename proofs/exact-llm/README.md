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
python exact_llm.py check --model SmolLM2-360M      # exact-16 on three routes against expected-16-SmolLM2-360M.sha256
python exact_llm.py check --model SmolLM2-1.7B --routes f64 --no-float   # one route, no float32: a hash run of 9 to 57 min on the runners
```

Rows 1 to 6: GitHub Actions run [43671156245](https://github.com/lmtlssss/speedrunpapi/actions/runs/43671156245) (`.github/workflows/exact-llm.yml`, Python 3.12, NumPy 2.5.4). Row 7: Apple M1, Python 3.11.18, NumPy 2.4.6 with Accelerate, onnxruntime 1.32.0. Full hashes and every printed line: `record/machines.txt`. Batch 8, 0 values clamped on every machine.

## exact-16: every product operand a 16-bit integer

`Exact16` in `exact_llm.py`. Every operand of every matrix product is an integer within ±(2^15 − 1), each with its own power-of-two scale; the work between products is the exact model's. A product over n inputs is then exact on three routes, and the routes give the same bits. The bound depends on n alone, not on the weights or the clamps.

| route | the product | exact while | engine |
| --- | --- | --- | --- |
| f64 | one float64 product | n · (2^15 − 1)^2 < 2^53 | `exact16-f64` |
| f32 | `a = 256 a1 + a0`, `a0` in [−128, 127], `a1` in [−128, 128], the same for `b`; four float32 products in chunks of 1,024 inputs | partial sums ≤ 1,024 · 2^14 = 2^24 | `exact16-f32` |
| i8 | `u = a + 2^15` in [1, 2^16 − 1], `u = 256 u1 + u0`, both uint8, the same for `b`; four int32 products of uint8 by uint8, onnxruntime `MatMulInteger` (NumPy int32 where onnxruntime is missing, named `i8-numpy`); `a · b = u_a · u_b − 2^15 (Σ a + Σ b) − n 2^30` in int64 | n · 255^2 < 2^31, n ≤ 33,025 | `exact16-i8` |

`a · b` (on i8, `u_a · u_b`) `= 2^16 G11 + 2^8 (G10 + G01) + G00`, `Gij = ai · bj`, added in int64; `mm16`. `MatMulInteger` is a one-node ONNX model (opset 13) written as protobuf bytes in `exact_llm.py`.

What a kernel may hold inside, in any order and grouping (`bounds-16.json`, `kernel_intermediate`):

| route | largest partial sum | why no step rounds or saturates |
| --- | --- | --- |
| f64 | n · (2^15 − 1)^2 < 2^53 | every product and every partial sum is an integer below 2^53, and every integer below 2^53 is a float64; a sum or a fused `a · b + c` whose exact value is a float64 is returned exactly, so the order, the blocking and FMA cannot change it |
| f32 | 1,024 · 128 · 128 = 2^24 within a chunk | every digit product is an integer with \|p\| ≤ 2^14 and every partial sum of a chunk, in any order, an integer with \|s\| ≤ 2^24; every integer with \|s\| ≤ 2^24 is a float32. The digits have at most 8 significant bits, so they are exact as TF32 and bfloat16 inputs too, with float32 accumulation (not run here) |
| i8 | a pair 2 · 255^2 = 130,050; k products ≤ k · 255^2 < 2^31 for k ≤ 33,025 | one uint8 · uint8 product (up to 65,025) does not fit a signed 16-bit lane, so the kernel widens before it adds. uint8 by uint8 is the pair every onnxruntime version implements |

The i8 route first used `a >> 8` as int8 with `a & 255` as uint8. A uint8 · int8 kernel without VNNI adds adjacent pairs in int16 with saturation, and 2 · 255 · 128 = 65,280 > 32,767; a 7-bit unsigned digit (2 · 127 · 128 = 32,512) would hold, at six products instead of four. onnxruntime's quantization notes ([When and why do I need to try U8U8?](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html#when-and-why-do-i-need-to-try-u8u8)): on x86-64 with AVX2 and AVX512 it "uses the VPMADDUBSW instruction for U8S8", whose output "has to be clamped (saturated)" when it does not fit 16 bits, and "the U8U8 format ... doesn't have saturation issues". The runner that failed did so earlier still: onnxruntime 1.23.2, the last macOS x86-64 wheel, cannot build a `MatMulInteger` session for one of the pairs with an int8 operand (`NOT_IMPLEMENTED`, run 43720517570).

| Apple M1, 64 prompts | logits | continuations | clamped |
| --- | --- | --- | --- |
| `exact16-f64`, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-f32`, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-i8`, onnxruntime 1.32.0, batch 8 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |
| `exact16-f64`, batch 1 | `b0cc875f…0b4460` | `a800ebad…7613cc` | 0 |

The continuations are the exact model's and float32's. `python exact_llm.py check` runs the three routes against `expected-16.sha256`; exit 1 if any route differs. Full hashes: `record/exact16-m1.txt`.

| seven machines, 64 prompts, batch 8 | Python | NumPy | onnxruntime | f64 | f32 | i8 |
| --- | --- | --- | --- | --- | --- | --- |
| ubuntu-latest, Linux x86-64 | 3.12.16 | 2.5.4 | 1.32.0 | 88 s | 177 s | 134 s |
| ubuntu-24.04-arm, Linux AArch64 | 3.12.16 | 2.5.4 | 1.32.0 | 76 s | 167 s | 127 s |
| macos-latest, macOS arm64 | 3.12.10 | 2.5.4 | 1.32.0 | 112 s | 295 s | 136 s |
| macos-15-intel, macOS x86-64 | 3.12.10 | 2.5.4 | 1.23.2 | 252 s | 545 s | 290 s |
| windows-latest, Windows x86-64 | 3.12.10 | 2.5.4 | 1.32.0 | 168 s | 631 s | 328 s |
| windows-11-arm, Windows ARM64 | 3.12.10 | 2.5.4 | 1.32.0 | 117 s | 311 s | 170 s |
| Apple M1, macOS arm64 (Accelerate) | 3.11.18 | 2.4.6 | 1.32.0 | 80 s | 248 s | 206 s |

Every cell printed logits `b0cc875f…0b4460` and continuations `a800ebad…7613cc`, MATCH, 0 clamped: 21 runs on seven machines, one pair, across Python 3.11.18 to 3.12.16, NumPy 2.4.6 and 2.5.4 and onnxruntime 1.23.2 and 1.32.0. Seconds are the hash run of each route. Rows 1 to 6: GitHub Actions run [43736296963](https://github.com/lmtlssss/speedrunpapi/actions/runs/43736296963) at `fdeb23b`, where the exact model also printed its pair (`30ed613b…cee773`) on every runner; every printed line: `record/exact16-machines.txt`.

| exact-16, in the order `Exact16` computes | |
| --- | --- |
| weights | `w16 = rint(w · 2^g)` from the bfloat16 values, `g` per output row the largest with every entry within ±(2^15 − 1) (the tied embedding: one `g` per token); int16 `.npy`, memory-mapped; `int16_weights` |
| product inputs | made once for every product that reads them (`h` for q, k and v; `h` for gate and up), clamped, peeled and block-shifted; `prepare` |
| block shift | per token vector: `sh = max(0, bitlength(max \|x\|) − 15)`, `x16 = round(x / 2^sh)`; a second rounding at `sh + 1` only for the vectors whose first reached 2^15; `block16` |
| peeled terms | 2 per product, per token vector: its two largest \|x\| (ties to the lower index) kept whole; each `x · w16` is an exact wide term added in int64 before the one rounding, on every route; `peel_index` |
| linear, logits | `y = round((2^sh · x16 · w16 + Σ peeled x · w16) / 2^g)`, one rounding; `product` |
| key-value cache | each position's `k` clamped and block-shifted (`k16` and its shift), `v` clamped and split, once, as the position enters the cache; `cache_entry` |
| scores | `q16 · k16`, `q` and `k` block-shifted per head vector; `s = 2^(sh_q + sh_k) · q16 · k16` at 2^-32 |
| softmax | as the exact model, then `p = round(floor(e · 2^16 / Σ e) / 2)` at 2^-15, held at 2^15 − 1 (20,174 values over the 64 prompts at batch 1) |
| context | `v` whole, `v = 2^15 vh + vl`, `vl = v & (2^15 − 1)`, `\|vh\| ≤ 2^13` within the clamp; `round((2^15 · p16 · vh + p16 · vl) / 2^15)` at 2^-16. No shift, so no position reads another key's magnitude, a later token or the padding |
| clamps | by rule, per site, for each model: the largest power of two at which every int64 operation of exact-16 stays below its limit, from the config and the 16-bit weights' largest column sum and row scales (`clamps16`, `weight_stats16`); no constant per model. The exact model keeps its own clamps |
| everything else | the exact model's: norms, rotary, the exp and SiLU tables |

| product, `bounds16.py` | inputs n | f64, below 2^53 | f32, chunk, at most 2^24 | i8, below 2^31 |
| --- | --- | --- | --- | --- |
| q, k, v, o, gate, up, logits | 576 | 2^39.170 | 576, 2^23.170 | 2^25.159 |
| down | 1,536 | 2^40.585 | 1,024, 2^24.000 | 2^26.574 |
| scores q·k | 64 | 2^36.000 | 64, 2^20.000 | 2^21.989 |
| context p·vh, p·vl | 512 keys at most | 2^39.000 | 512, 2^23.000 | 2^24.989 |

Weight row scales `g`: q 12..19, k 12..18, v 13..17, o 12..17, gate 11..16, up 12..16, down 12..16, embedding 14..16. 40 int64 operations around the products, each below its limit: `bounds-16.json`. The largest is the scores row, 2^63 − 2^49 + 2^33; it sets the clamps of q and k.

| site | clamp by rule (real units) | 135M: peak, margin | 360M: clamp, peak, margin |
| --- | --- | --- | --- |
| residual | 2^25 | 19,509.485, 2^10.75 | 2^25, 24,019.595, 2^10.45 |
| attention input | 2^17 | 11.429, 2^13.48 | 2^17, 10.373, 2^13.62 |
| o input | 2^23 | 9.531, 2^19.75 | 2^22, 11.628, 2^18.46 |
| mlp input | 2^23 | 28.742, 2^18.16 | 2^22, 28.731, 2^17.16 |
| down input | 2^22 | 2,630.720, 2^10.64 | 2^21, 2,799.645, 2^9.55 |
| logits input | 2^23 | 53.630, 2^17.25 | 2^22, 68.984, 2^15.89 |
| q, k | 2^10 | 22.075 and 22.910, 2^5.48 | 2^10, 21.295 and 21.260, 2^5.59 |
| v | 2^13 | 12.972, 2^9.30 | 2^13, 19.220, 2^8.73 |
| gate, up | 2^15 | 50.741 and 72.026, 2^8.83 | 2^15, 117.465 and 215.929, 2^7.25 |

0 values clamped in every run of either model. Each clamp is the largest power of two at which every int64 row of `bounds16_rows` stays below its limit (q and k together, gate and up together), from the config and the 16-bit weights' largest column sum and row scales; a wider model gets narrower product-input clamps. The peaks are those of the 64 prompts on the M1 (`record/peaks-16.json`, `record/peaks-16-SmolLM2-360M.json`). The exact model keeps its own clamps (`bounds.py`); the 135M's exact-16 pair is the same under these clamps as under the exact model's, since nothing reached either.

### The width, measured

Each row narrows the exact model's product operands and is compared with the same float32 run (perplexity 30.5717); Apple M1, 0 values clamped in every row. Inputs: product inputs per token vector; weights: per output row from bfloat16; attention: q and k per head vector, p at 2^-15. In these rows `v` had one shift per key-value head over all keys; exact-16 takes `v` whole in two halves (last row). Peel k: the k largest \|x\| of each product input kept whole. The 14- and 12-bit rows are the edge.

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

## t3: the products by adds and subtracts

A fourth route, `exact16-t3`, run where a C compiler is installed (`check --routes t3`; not in check's default three). Every product of exact-16's forward pass is computed by `t3.c`, whose arithmetic is add, subtract, shift by a constant and bitwise logic: the matrix products in `mm16` (q, k, v, o, gate, up, down, logits, the scores q16·k16, the context p·vh and p·vl), the peeled terms, and the element-wise products (the norm's squares and weight, rotary, the exp and SiLU interpolations, SiLU(gate)·up) through `Exact.mul`. Divisions (52,477 per token) and square roots (61) stay as on the other routes: NumPy's `//` and float `sqrt`, each checked by an integer bracket that NumPy multiplies (q·d ≤ n < (q + 1)·d, s² ≤ n < (s + 1)²). Shifts by a computed amount (the block shift, the row scale) stay NumPy's too.

| signed digits, `t3.c` | for m ≥ 0: `h = m >> 1`, `s = m + h`, `c = h ^ s`; plus `s & c`, minus `h & c`; m = plus − minus, non-adjacent form; a negative value by its magnitude with plus and minus exchanged |
| --- | --- |
| stream | a 16-bit word per instruction, `op << 14 \| i`; per output row, for digit position k = 15 down to 0: `ADD i` for each input with digit +1 at k, `SUB i` for each with −1, then `STEP` (`EMIT` at k = 0) |
| machine | per lane: `s` (int32), `acc` (int64). `ADD i`: s = s + x[i]. `SUB i`: s = s − x[i]. `STEP`: acc = acc + acc; acc = acc + s; s = 0. `EMIT`: `STEP`, then y[row] = acc, acc = 0. 8 lanes at a time |
| weights | each matrix compiled to its stream once (924,918,488 bytes for the 135M: 459,184,492 digits and 16 words for each of 204,672 output rows), kept in `$EXACT_LLM_T3` (default `.cache/t3`), one folder per `t3.c` and model |
| activations | the right operand recoded into digits at each product: k16 for the scores, vh and vl for the context, the smaller-magnitude operand element-wise and for the peeled terms |

| Apple M1, 64 prompts, batch 8, one `check` process | logits | continuations |
| --- | --- | --- |
| `exact16-f64` | `b0cc875f…0b4460` | `a800ebad…7613cc` |
| `exact16-t3`, 8 threads | `b0cc875f…0b4460` | `a800ebad…7613cc` |

MATCH on both, 0 clamped. The M1 was shared with other jobs during this run, so its seconds are not a measure of either route. Per token at the last position (context 64, `t3_count.py`, the kernel's counters): 459,184,492 digit adds and subtracts in the weight products, as the digit census predicts, and 6,549,504 Horner adds; 1,408,559 and 6,442,304 in the peeled terms; 11,875,560 and 1,658,880 in the attention (scores 5,007,459, p·vh 900,330, p·vl 5,967,771, Horner 552,960 each); 1,271,526 and 4,451,136 element-wise; 492,841,961 adds and subtracts in all. `t3_nomul.py`: the kernel's disassembly holds no multiply, multiply-add or divide instruction and calls no library multiply or divide (Apple clang, arm64: 0 of 511 instructions, 496 in the five functions of `t3.c` and 15 in its call stubs). It does report the `mul` in `t3.c` built without its `KEEP` barriers, and the calls `__mulsi3` (a multiply built for rv32i) and `___divti3` (a 128-bit divide on arm64 macOS). `t3_rv32.c`: the stream machine, freestanding, compiled for rv32i (no M extension) by LLVM: 45 instructions, none a multiply, no library multiply; compiled only, not run.

## Larger models

One code path: the sizes come from each model's pinned `config.json`, the clamps by rule from its own weights (above), the bound per route from the width. `python exact_llm.py check --model SmolLM2-360M` runs exact-16 on its three routes, float32 and onnxruntime.

| model | weights | exact-16 pair (logits / continuations) | machines × routes printing it | top-1 against float32 | continuations equal | largest logit difference | Apple M1, tokens/s: exact-16 f64, float32 (prefill; decode batch 8) | peak resident, exact-16 f64 |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| SmolLM2-135M | 134,515,008 | `b0cc875f…0b4460` / `a800ebad…7613cc` | 7 × 3 | 471 of 471 | 64 of 64 | 0.0592 | 121; 44.5 and 1,037; 130.1 | 926 MB |
| SmolLM2-360M | 361,821,120 | `d97a67da…2eddfe` / `f84819ca…4b1aa4` | 7 × 3 | 471 of 471 | 64 of 64 | 0.0847 | 70; 20.6 and 190; 14.8 | 1,537 MB |
| SmolLM2-1.7B | 1,711,376,384 | `eee059ce…321bb7` / `f4787fa5…182340` | 6 runners, 13 runs (table below) | 471 of 471 | 64 of 64 | 0.1477 | not run on the M1 | not measured |

Machines: the six runners of GitHub Actions run [43754428621](https://github.com/lmtlssss/speedrunpapi/actions/runs/43754428621) (Python 3.12.10 and 3.12.16, NumPy 2.5.4, onnxruntime 1.23.2 and 1.32.0), where the 135M's exact pair also matched on every runner, and the Apple M1 (Python 3.11.18, NumPy 2.4.6). 0 values clamped in all 42 runs. The distance is the M1's; on the runners the 360M's largest logit difference is 0.0842 to 0.0847. Every printed line: `record/ci-43754428621.txt`, `record/exact16-360m-m1.txt`.

The bound at each size, per route: the widest product is the down projection, 1,536 inputs at 135M and 2,560 at 360M. On f64 its partial sums stay below 2^40.585 and 2^41.322, under 2^53 with no chunk. On f32 the down projection is the one product wider than 1,024 inputs, so it alone is chunked: 30 matrices at 135M, 32 at 360M. On i8 the sums stay below 2^26.574 and 2^27.311, under 2^31.

At 360M on the M1 float32 decodes slower at batch 8 (14.8 tokens/s) than at batch 1 (17.3), and slower than exact-16. The cause is not the machine's memory: there was no swapping, but 11.0 of its 44.6 s went to the kernel in 1,654,651 page reclaims, against 1.65 s and 120,153 for exact-16. So the time goes to fresh allocations in this baseline's NumPy decode step; that is not looked into yet.

### SmolLM2-1.7B, on the runners

24 layers, width 2,048, 32 heads, feed-forward 8,192, rotary base 130,000 (its cos and sin tables are in `tables/`). It runs on the runners only, one route per job: GitHub Actions run [43759765827](https://github.com/lmtlssss/speedrunpapi/actions/runs/43759765827), 14 jobs with a limit of 120 minutes each. 13 jobs printed the exact-16 pair, and all 13 printed the same one: logits `eee059ce…321bb7`, continuations `f4787fa5…182340`, now pinned in `expected-16-SmolLM2-1.7B.sha256`. The 13 printed the same peaks and clamps, and 0 values were clamped.

| runner | f64 | f32 | i8 |
| --- | --- | --- | --- |
| ubuntu-latest, Linux x86-64 | 828 s; float32 ran past the limit | 3,933 s | 1,604 s |
| ubuntu-24.04-arm, Linux AArch64 | 558 s; float32 2,520 s | 1,598 s | 1,092 s |
| macos-latest, macOS arm64 | 1,226 s; float32 3,834 s | did not finish within the limit | 4,816 s |
| macos-15-intel, macOS x86-64 | 3,388 s; float32 ran past the limit | 6,231 s | 3,656 s |
| windows-latest, Windows x86-64 | 2,454 s; float32 ran past the limit | not run | not run |
| windows-11-arm, Windows ARM64 | 1,472 s; float32 4,301 s | not run | not run |

Seconds are the hash run of the exact-16 route. Before it, the 16-bit weights, int32 embedding and norms and weight statistics took 67 to 294 s, after the download. Python 3.12.10 and 3.12.16, NumPy 2.5.4 and 2.5.5, onnxruntime 1.23.2 and 1.32.0.
- float32, against which the distance is measured, keeps bfloat16 bits and widens one matrix at each use (above 4 GB of float32 weights). On the M1 at 135M the widened run and the run with whole float32 weights give the same bits.
- Where float32 finished, 471 of 471 prompt positions agree on top-1 and 64 of 64 continuations are equal. The largest logit difference is 0.1477 on ubuntu-24.04-arm and windows-11-arm and 0.1474 on macos-latest.
- onnxruntime is skipped: onnx-community publishes no export of this model.

The workflow runs each 1.7B job that finished here:
- f64 on all six runners, float32 only beside it on ubuntu-24.04-arm (53 minutes);
- f32 on ubuntu-latest and ubuntu-24.04-arm;
- i8 on ubuntu-latest, ubuntu-24.04-arm and macos-15-intel.

The f32 jobs on macos-latest and macos-15-intel are left out because they ran past 120 minutes: on macos-latest the exact-16 stage alone in run 43759765827, on macos-15-intel in run [43777602992](https://github.com/lmtlssss/speedrunpapi/actions/runs/43777602992) after 6,231 s in the first. The i8 job on macos-latest is left out too: it took 4,816 s in run 43759765827 and ran past 120 minutes twice in run [43806351228](https://github.com/lmtlssss/speedrunpapi/actions/runs/43806351228). Every printed line: `record/ci-43759765827.txt`.

The bound at 1.7B: the widest product is the down projection, 8,192 inputs. On f64, 8,192 · (2^15 − 1)^2 < 2^43, under 2^53. On f32 every product at 1.7B is wider than 1,024 inputs, so every one is chunked: 2 chunks at width 2,048 and 8 for the down projection. On i8, 8,192 · 255^2 < 2^29, under 2^31, and n ≤ 33,025.

## Distance to float32

| | exact | exact-16 | onnxruntime |
| --- | --- | --- | --- |
| prompt positions with the same top-1 token as float32 | 471 of 471 | 471 of 471 | 471 of 471 |
| largest \|logit − float32 logit\|, Apple M1 | 0.0215 | 0.0592 | 0.0006 |
| mean \|logit − float32 logit\|, Apple M1 | 0.0012 | 0.0027 | 0.00002 |
| largest and mean, the six runners | 0.0215 to 0.0217, 0.0012 | | |
| continuations, 64 × 48 tokens, equal to float32 | 64 of 64 | 64 of 64 | 64 of 64 |
| text, 8,176 tokens: same top-1 token as float32 | 8,160 (99.80 %) | 8,171 (99.94 %) | 8,176 (100 %) |
| perplexity, float32 30.5717; Apple M1, float64 exp and log of the logits, not hashed | 30.5799 | 30.5715 | 30.5717 |
| 256-token continuations, 64 prompts, batch 8, equal to float32 (16,384 tokens) | 64 of 64 | not run | 64 of 64 |

Text: Tiny Shakespeare (`karpathy/char-rnn` at `370cbcd`), the first 8,192 tokens as 16 windows of 512. `distance.py`, `record/machines.txt`. Every float32 figure in this README is the one run `exact_llm.py text --engine float32` on the M1: perplexity 30.571749784 (printed 30.571750), 30.5717 to four places; onnxruntime 30.571742606, exact 30.579936034, exact-16 30.571460960.

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
| exact-16, f64 route | 121 | 44.5 | 7.7 | 926 MB |
| exact-16, f32 route | 79 | 13.5 | 1.9 | 887 MB |
| exact-16, i8 route (onnxruntime 1.32.0) | 54 | 18.2 | 2.9 | 855 MB |

`speed.py`. The 64-prompt hash run at batch 8: exact 61.7 s at 831 MB (default), 38.9 s at 1.82 GB (`--keep`); float32 28.3 s; onnxruntime 22.6 s; exact-16 f64 80 s, f32 248 s, i8 206 s (`check`, 1.21 GB for the whole check). The 256-token run of the 64 prompts, exact, batch 8: 345 s at 1,496 MB. The i8 route with the int8-by-uint8 digits it replaces decoded 8.2 tokens/s at batch 8 (`record/exact16-m1.txt`, run 1).

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
| linear | `round(clamp(x) · W / 2^16)`, `clamp(x)` made once for every product that reads it (`prepare`), `W` [in, out] float64 from int32; the down product in 6 chunks of 256 inputs, each in float64, summed in int64; `linear` |
| rotary, `i < 32` | `x'_i = round((x_i·C[p,i] − x_{i+32}·S[p,i]) / 2^20)`; `x'_{i+32} = round((x_{i+32}·C[p,i] + x_i·S[p,i]) / 2^20)`; `rope` |
| key-value cache | `clamp(k)` and `clamp(v)` of each position, made once as it enters the cache (`cache_entry`); cos and sin of each position read once per forward pass (`rope_tables`) |
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
| `model.safetensors`, `tokenizer.json`, `config.json` | `HuggingFaceTB/SmolLM2-360M` @ `f8027fd0eaeea54caa13c31d31b9fdc459c38b49` | `7aaff666…`, `9ca9acdd…`, `34f78014…` |
| `onnx/model.onnx` | `onnx-community/SmolLM2-360M-ONNX` @ `539c1088be2dcd673c39059d25a6bc4aec625504` | `09c21171…` |
| `model.safetensors`, `tokenizer.json`, `config.json` | `HuggingFaceTB/SmolLM2-1.7B` @ `effd688a12921b4cc83e3312b6feb579f70f9c71` (onnx-community publishes no export of it) | `11935289…`, `9ca9acdd…`, `33397f6a…` |
| prompts: `sentence1` of the first 64 lines of `test.jsonl.gz` | `mteb/stsbenchmark-sts` @ `96943a16ea6a35129e253c659081cb59daf81b30` | `524a7513…` |
| text: `data/tinyshakespeare/input.txt` | `karpathy/char-rnn` @ `370cbcd448eb7daf32f21a6be560b70e0b33c4e3` | `86c4e6aa…` |

## Checks

| check | result | command |
| --- | --- | --- |
| tokenizer against `tokenizers` 0.23.3: 64 prompts, 2,000 text lines, the 2,000 lines as one string | 0 differences, 33,097 tokens | `compare_tokenizer.py` |
| tables against their generator | equal | `make_tables.py --check` |
| products below 2^53, int64 below 2^63 | holds | `bounds.py` |
| exact-16: every product within its route's bound, int64 below 2^63 | holds | `bounds16.py` |
| exact-16 routes against int64 products: 7 shapes (2-D and the batched attention shapes, widths 1,023 to 1,536 across the f32 chunk edge) × 6 operand kinds (random; all +max, which puts every i8 digit at 255 and every f32 chunk at exactly 2^24; all −max; +max by −max; p-like; digit extremes, the eight values whose digits sit at the ends of both routes' ranges, mixed position by position), int64 and int16 right operands | 0 different on all three routes; the int16 digit splits equal the int64 ones for all 65,535 values; peel ties to the lower index | `routes_test.py` |
| the spare row on synthetic operands: `locate()` on 2,000 single errors; a product of 96 inputs and 300 outputs and the attention of the 135M's heads, checked against Exact16's; 300 single faults each in a product's sums, weights and inputs and in the attention's sums, inputs and looks | 2,000 placed; checked equals Exact16's, no check fired; every fault caught, and with repair every output equals Exact16's | `spare_row_test.py` |
| float32 against onnxruntime | top-1 equal at all 471 prompt and 8,176 text positions; largest logit difference 0.0006 | `distance.py DIR float32 onnx` |
| notebook, its cells run as one script in a fresh directory with an empty cache, Apple M1 | downloads checked; exact MATCH (63 s); top-1 471 of 471; continuations 64 of 64 | `exact_llm.ipynb`, `make_notebook.py --check` |

## The spare row: every product checked, a single wrong output found and computed again

`spare_row.py` runs exact-16 with every product and every look checked as it is made, and corrects a single wrong value where the check can place it. The checks compute nothing new: with all of them on, the 64 prompts give exact-16's pair on each of the three routes.

| check | how |
| --- | --- |
| products over the weights: q, k, v, o, gate, up, down, logits | T = x W in exact integers obeys, for each row of x, Σ_j T_j = x · c1 and Σ_j j·T_j = x · c2, with c1_i = Σ_j W_ij and c2_i = Σ_j j·W_ij (j = 1 … n), the two spare rows, made once from the stored weights. They are compared in int64 with wrap-around, that is modulo 2^64, with no tolerance |
| products over the cache: the scores q · k, the context p · vh and p · vl | the same two sums. For each key and each v they are kept beside the cache as it is entered (64 adds each per new position) |
| placing and repair | a single wrong output j gives e1 = e and e2 = j·e. With e = 2^k·u, u odd: j = (e2 / 2^k)·u^−1 modulo 2^(64 − k), unique while n < 2^(64 − k). That output is computed again from the stored weights and rounded |
| product inputs | the spare rows cannot see an input read wrongly, because the product and its spare rows read the same wrong value. So the sum of each input vector is formed where the vector is made (`prepare`: `h` for q, k and v; `h` for gate and up). The product that reads it forms the same sum as one more row of ones; a wrong read is read again. The sum covers every word the product reads: the 16-bit values, the peeled values and their places, the shift |
| looks | rounding, bit length, division and square root by their brackets (y·2^k − 2^(k−1) ≤ v < y·2^k + 2^(k−1); 2^(b−1) ≤ a < 2^b; q·d ≤ n < (q + 1)·d; s² ≤ n < (s + 1)²); the split of v by putting it back together (v = 2^15·vh + vl); the clamps, the held p, the table reads (exp, SiLU, cos and sin), the peel selection and the softmax maximum made twice and compared |

**Caught and not placed.** An error whose lowest set bit k is so high that n·2^k reaches 2^64, for a product of n outputs, cannot be placed. The check fires and the row is left as it is. For a single flipped bit that means bit 49 or above of an int64 sum of the logits (49,152 outputs), bit 55 in q's 576, bit 58 in the context's 64. In the campaign's clean run no product sum is wider than 43 bits (`record/spare-campaign.json`, `widths`). So only a flip in the high bits that no sum uses can land there, and none in the campaign below did.

| SmolLM2-135M, Apple M1, 64 prompts, batch 8 | every check off (`--plain`) | every check on |
| --- | --- | --- |
| route f64 | `b0cc875f…0b4460` / `a800ebad…7613cc` MATCH | the same pair, MATCH; no check fired |
| route f32 | the same pair, MATCH | the same pair, MATCH; no check fired |
| route i8 | the same pair, MATCH | the same pair, MATCH; no check fired |

**What the checks cost**, per token on SmolLM2-135M, at the last position of a 64-token context:
- steps (the multiply-adds of the products): 138,414,912 → 139,220,620, that is +805,708 (+0.58%);
- looks (each value read for its magnitude: roundings, clamps, comparisons, bit lengths, divisions, square roots, table reads): 2,108,400 → 4,366,005, that is +2,257,605 (+107.08%).

The census is `count_spare.py`, then `report_spare.py` (`record/census-spare.json`, `record/census-spare.md`). It counts every NumPy operation of the forward pass with and without the checks, on zero weights of the pinned shapes: no count depends on a value. `report_census.py` gives the rules that sort each operation into steps, looks and the rest.

Checks made in each checked run: spare rows 115,584; input sums 104,064; rounding brackets 256,534; division brackets 58,368; square root brackets 23,424; bit length brackets 92,928; clamps made twice 127,488; peel selections made twice 46,464; table reads made twice 23,808; softmax maxima made twice 11,520; held p made twice 11,520; v splits put together 11,520.

Fault campaign: one fault per run, 100 runs of each kind, each run against its clean run. Route f64, prompt 0 (7 tokens) and 4 generated tokens. The fault is armed at an element drawn at random among the run's fault points of its kind (looks 7,987,600; product inputs 1,707,230; weights 537,919,488; product sums 2,412,840), at a bit drawn within the largest bit length seen at that site in the clean run (16 for a weight). Seed 1.

| fault | injected | changed a logit | changed a token | caught | caught by | repaired, hash equal to the clean run's |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| one bit of one product sum | 100 | 52 | 0 | 100 | spare rows 100 | 100 |
| one bit of one weight as it is read | 100 | 64 | 0 | 100 | spare rows 100 | 100 |
| one bit of one product input as it is read | 100 | 91 | 4 | 100 | input sums 100 | 100 |
| one bit of the result of one look | 100 | 92 | 16 | 100 | clamp made twice 34; rounding bracket 48; division bracket 7; table read made twice 6; v split put together 5; held p made twice 1 | 100 |

Not caught and changed a logit: 0 of 400. The column "changed a logit" is the run without repair. Every line: `record/spare-m1.txt`; every fault, with its site, bit and values: `record/spare-campaign.json`.

Commands:
- `python spare_row.py hash --route f64` (or `f32`, `i8`; add `--plain` for every check off);
- `python spare_row.py campaign --n 100 --seed 1 --route f64`;
- `python count_spare.py . census-spare.json`, then `python report_spare.py census-spare.json`: the census and its tables. It reads the pinned config.json only, and takes 10 s on the M1;
- `python spare_row_test.py`: synthetic operands, no model weights. It checks `locate()`, the checked product and attention against Exact16's, and faults of each kind caught and repaired.

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
| `bounds16.py`, `bounds-16.json`, `bounds-16-SmolLM2-360M.json` | the exact-16 bound per route, the clamps by rule, the peaks and margins, per model |
| `expected-16-SmolLM2-360M.sha256`, `record/exact16-360m-m1.txt`, `record/ci-43754428621.txt` | the 360M's pair; every line of its M1 run; every line of the twelve jobs (135M and 360M on six runners) |
| `expected-16-SmolLM2-1.7B.sha256`, `record/ci-43759765827.txt` | the 1.7B's pair; every line of its 14 jobs (one route each), with each job's end and wall time |
| `record/peaks-16.json`, `record/peaks-16-SmolLM2-360M.json` | each site's peak, clamp, margin and clamped count, from `check --peaks` |
| `routes_test.py` | the three routes against int64 products; t3 too where a C compiler is installed, with every 16-bit value through the stream and 200,081 element-wise pairs |
| `t3.c`, `t3_nomul.py`, `t3_count.py`, `t3_rv32.c` | the t3 kernel; its disassembly checked for multipliers; its counters per token; the stream machine for rv32i |
| `spare_row.py`, `spare_row_test.py`, `record/spare-m1.txt`, `record/spare-campaign.json` | exact-16 with every product and look checked, the fault campaign; its test on synthetic operands; every line of the M1 runs; every fault of the campaign |
| `count_ops.py`, `report_census.py`; `count_spare.py`, `report_spare.py`, `record/census-spare.json`, `record/census-spare.md` | the census of every NumPy operation per token, sorted into steps and looks: of exact and exact-16; of exact-16 with and without the spare-row checks, and its tables |
| `measure16.py`, `record/exact16-table.txt` | the width table, one row per run |
| `expected-16.sha256`, `record/exact16-m1.txt`, `record/exact16-machines.txt` | the two exact-16 hashes; every exact-16 line of the M1; every line of the six runners, run 43736296963 |
| `make_tables.py`, `tables/` | the tables: exp, SiLU, and cos and sin for the rotary bases 100,000 and 130,000 |
| `same_bits.py` | 1 and 4 threads × batch 1 and 8, any engine |
| `long_run.py` | 256-token continuations |
| `distance.py` | exact against float32 |
| `speed.py` | tokens/s and peak memory |
| `compare_tokenizer.py` | the tokenizer against `tokenizers` |
| `exact_llm.ipynb`, `make_notebook.py` | the notebook, NumPy only |
| `pins.json`, `expected.sha256` | pins, one block per model; the two exact hashes |
| `record/machines.txt` | every line of the seven machines |

## Your model

One model of yours, up to 500 million parameters, made exact this way: 1,800 USD, fixed.

You send the model's name and revision, the inputs you care about and the machines it must agree on. You receive the code, the hashes, and the comparison against float32 as in the tables above.
Full refund if two of your machines print different hashes.

Pay: https://buy.stripe.com/4gM8wO3Ho0c7dUubo76c007 · Questions: lmtlssss@colony.technology

Larger work, by contract: the same address.
