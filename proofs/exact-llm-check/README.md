# Exact LLM check: SmolLM2-135M without its matrix products

A checker for a claimed run of `../exact-llm` (SmolLM2-135M in integer arithmetic). The prover runs the model and sends a trace: the exact integer sum of every matrix product before its rounding shift. The checker then:
- checks each matrix product against the pinned weights by Freivalds' identity, without computing it;
- recomputes every other step itself: embedding, clamps, RMS norm, rotary step, softmax, SiLU, rounding shifts;
- takes the greedy tokens from the checked logits and requires them to equal the claimed continuation.

`check.py` is written from the method table of `../exact-llm/README.md` and shares no code with `exact_llm.py`. It reads the pinned files itself (sha256 against `pins.json`) and has its own bf16 → integer conversion and its own tokenizer. `trace.py` is the prover: it imports `exact_llm.py` unchanged.

```sh
pip install numpy
(cd ../exact-llm && python exact_llm.py check)   # fills the model cache; EXACT_LLM_CACHE as there
python reproduce.py                              # exit 0; 290.5 s and 1.42 GB of disk on the Apple M1 below
```

Expected output, the same on every machine (times and full records go to `reproduce.jsonl`):

```
ok    prover: batch 0, 48 forward calls, 384 claimed tokens
ok    check, Freivalds logits: accept; 396 of 396 planted faults caught, 271 of 271 (kind, layer) places
ok    check, direct logits: accept
ok    wrong claimed token (row 0, token 0 := 199): reject: call 0, row 0 token 199 claimed, 198 computed
ok    wrong claimed token (row 3, token 10 := 199): reject: call 10, row 3 token 199 claimed, 198 computed
ok    wrong claimed token (row 7, token 47 := 505): reject: call 47, row 7 token 505 claimed, 504 computed
ok    commitment: 132222 leaves, 13524 units; units failing on the honest trace: 0
ok    commit and open, k = 16: 0 failing, 0 bad paths
ok    commit and open, k = 64: 0 failing, 0 bad paths
ok    commit and open, k = 256: 0 failing, 0 bad paths
ok    prover with model.layers.3.mlp.up_proj.weight:100:200 + 1: 384 of 384 tokens as honest; reject: call 0, up
ok      units failing: 438, all in layer [3]
ok    prover with model.layers.20.self_attn.v_proj.weight:5:100 + 1: 384 of 384 tokens as honest; reject: call 0, v
ALL AS EXPECTED
```

The first run also writes the integer weights to `w/` (514 MB); each trace of batch 0 with the leaves of `spot.py` is 904,161,024 bytes and is deleted after its checks. Every figure below is from `record/`, made with these scripts and `../exact-llm/exact_llm.py` at commit 52864a4. `reproduce.py` gives the output above at that commit and at this one, after #98.

## Planted faults and controls

The 64 prompts of `../exact-llm` in 8 batches of 8, 48 greedy tokens each: 3,479 tokens through the model, 384 claimed per batch.

| Case | Result | Record |
| --- | --- | --- |
| Honest traces, logits by Freivalds and logits direct | 16 of 16 accepted | `results.jsonl` |
| One integer of one product's sum changed by ±1, at random places | **1,000 of 1,000** caught (125 per batch; 96 – 104 per kind of product) | `results.jsonl` |
| The same at every (kind, layer): q, k, v, scores, contexts, o, gate, up, down in each of 30 layers, and the logits | **271 of 271** places caught (batch 0, 396 of 396 faults with 125 random) | `reproduce.txt` |
| A faulty trace file on disk (q, scores, contexts, down, gate, logits) | 6 of 6 rejected | `controls.jsonl` |
| Wrong claimed token: first, middle and last | 3 of 3 rejected | `controls.jsonl` |
| A prover with one weight changed by one unit: up_proj of layer 3 [100, 200]; v_proj of layer 20 [5, 100] | Each prints **the same 384 tokens** as the honest run. Each is rejected at the first forward call, at up and at v. | `controls.jsonl` |

`test_f64.py`: `exact_mod` equal to Python integers in 28 of 28 cases (`test_f64.txt`).

## Operations per token

Measured counters over the 8 batches, divided by 3,479 tokens (`tally.txt`, `estimate.txt`):

| | Multiply-adds and element operations per token |
| --- | --- |
| The run itself | 135.6 million (135,585,792 at 32 keys) |
| Check, logits by Freivalds | **2.46 million** (1,678,033 products + 785,572 element-wise) |
| Check, logits direct | 31.55 million |
| Preparation, once per model: W r | 537,919,488 |

`estimate.py` gives the same counts from formulas, and for a 7-billion-parameter model.

## Wall time

Apple M1, 8 GB, macOS 27.2, Python 3.11.18, NumPy 2.4.6. The machine was shared with other jobs. 8 batches, 3,479 tokens.

| | Total s | Per batch: median (range) | Record |
| --- | --- | --- | --- |
| The run itself (`trace.py --plain`) | **76.35** | 9.52 (8.98 – 10.13) | `plain.jsonl` |
| Check, logits by Freivalds, one session (W r once: 4.23 s) | **57.96** | 5.93 (5.31 – 11.00) | `session_freivalds.jsonl` |
| Check, logits direct, one session (W r once: 3.81 s) | 64.70 | 7.67 (6.83 – 8.20) | `session_direct.jsonl` |
| Check, logits by Freivalds, a new process for each batch | 81.56 | 10.23 (8.21 – 12.17) | `results.jsonl` |
| Recording the trace (`trace.py`) | 109.32 | | `results.jsonl` |

In a session the checker draws r and prepares W r once, before any trace exists. Then for each batch it runs the prover as a separate process, whose time is not counted, checks the trace and deletes it.

## Trace size

| | Bytes | Per token |
| --- | --- | --- |
| 8 batches | 6,620,313,600 | 1,902,936 |
| Batch 0 | 839,022,336 | 1,915,576 |

Every value is int64. Batch 0 by kind: logits 179,306,496; gate and up 168,099,840 each; q, o, down and contexts 63,037,440 each; scores 29,341,440; k and v 21,012,480 each (`controls.jsonl`). The trace is written per batch and deleted after its checks.

## The identity and its error

S r ≡ x (W r) mod p for p ∈ {2^31 − 1, 2^31 − 19}, two random r per prime, drawn from `os.urandom` after the trace exists.
- Attention: scores by s r = q (Kᵀ r), with Kᵀ r updated as keys arrive; contexts by ctx r = p (V r).
- Every hint must first satisfy |S| ≤ 2^53. `../exact-llm/bounds.json` shows every true sum does; the largest bound, down_proj, is 2^52.25.
- So a wrong hint differs from the true sum by D with 0 < |Dᵢ| < 2^54 < p₁ p₂, and D is non-zero modulo p₁ or modulo p₂. For that prime, each random r misses D with probability at most 1/p.
- A wrong product passes with probability at most 2^-61.99. Over the 104,064 checks of the 8 batches, the union bound is 2^-45.3.

The mod-p products are float64 BLAS products on limbs (`exact_mod`). A is split into limbs of ka bits and v into limbs of kv bits, with ka + kv + ⌈log₂ n⌉ ≤ 52, so every partial sum is an exact integer.

## Commit and open k places (`spot.py`)

Instead of the trace, the prover sends a 32-byte Merkle root. After the root exists, the checker draws k of the U units at random, without replacement. The prover opens each leaf with its path. The checker verifies each unit from the root, the public layout and those openings only.

**Leaves.** For every token t and layer i < 30, there is one leaf for each of:
- r0, the clamped residual entering the layer;
- q, k, v, s, ctx, o, gate, up, down, each as its exact sum.

Each token also has a final leaf, and each token that predicts a claimed token has a logits leaf.

Leaf bytes are (call, row, slot, item code) as int32, then the int64 values. The leaf hash is sha256(0x00 ‖ bytes), a node is sha256(0x01 ‖ left ‖ right), and padding is sha256(0x02). The checker computes the leaf order from the prompts and the claim, and checks each opened header against it.

**Units.**
- **Unit (t, i).** It opens:
  - r0 to down of (t, i);
  - the next r0, or final(t);
  - k and v of every key t attends to.

  The checker recomputes the layer with the integer weights and requires the next residual to equal the opened leaf. At layer 0, r0 must also equal the embedding row of t's token.
- **Unit "logits", t.** The checker requires logits = clamp(RMS(final)) Eᵀ and the argmax to be the claimed token.
- **Binding.** Every input of a unit is a leaf that another unit checks as its output. Layer 0's input is bound to the public embedding and the claimed tokens.

Batch 0: 438 tokens, 132,222 leaves, depth 18, 847,553,520 leaf bytes, **U = 13,524 units**. Committing took 13.25 – 21.53 s (`spot.jsonl`).

| k | Leaves opened | Bytes sent | Checker s | Prover open s |
| --- | --- | --- | --- | --- |
| 16 | 940 – 1,139 | 2,653,520 – 3,439,760 | 0.161 – 1.485 | 0.453 – 0.660 |
| 64 | 3,356 – 4,096 | 9,731,168 – 11,869,760 | 0.373 – 1.238 | 0.748 – 1.881 |
| 256 | 11,651 – 12,708 | 37,664,384 – 41,053,496 | 1.197 – 3.814 | 3.471 – 5.876 |
| all: the trace itself | | 839,022,336 | 5.31 – 11.00 | |

The ranges are over 8 draws for each k: 3 on the honest trace and 5 on the changed-weight trace. Bytes include the paths and the root.

**Catch probability.** F is the number of failing units, measured by checking every unit. P = 1 − C(U − F, k) / C(U, k).

| Case | F | P, k = 16 | k = 64 | k = 256 | Spot runs |
| --- | --- | --- | --- | --- | --- |
| Honest trace | 0 | | | | 9 of 9 accepted, 0 bad paths |
| One integer of one product ±1 (200 faults, every kind) | **1** in 200 of 200 | 0.001183 | 0.004732 | 0.018929 | |
| Wrong claimed token, mid-sequence (3:10:199) | 2 (logits; embedding at layer 0) | 0.002365 | 0.009443 | 0.037502 | |
| Wrong claimed token, last (7:47:505) | 1 (logits) | 0.001183 | 0.004732 | 0.018929 | |
| One weight changed (up_proj of layer 3 [100, 200], +1) | **438** (every token's layer-3 unit) | 0.409664 | 0.879013 | 0.999799 | caught in 3 of 5, 4 of 5, 5 of 5 |

## Limits

- **The session is sound only because the prover never sees r.** Deployed, the checker's randomness must come after the trace or the root, and from outside the prover.
- **The check is shorter than the run only with logits by Freivalds and W r prepared once.** With logits direct and a new process for each batch, it is not.
- **Commit and open answers "is this the declared model?", not "is this one token right?".** A prover who wants one wrong token can put the whole lie into one unit, F = 1. A checker opening k units then catches it with probability k/U only, 0.0189 at k = 256. A changed weight fails every unit that uses it, F = 438. One wrong token still needs the full trace and the Freivalds check, which it passes with probability below 2^-45.
- **The binding argument relies on SHA-256.** By induction over (layer, token): if all units pass, every claimed token is the honest argmax, unless the prover finds a SHA-256 collision. Nobody else has reviewed the argument.
- In `spot.py` the draw is made in the same process as the prover's opening. Units are checked with direct products, not Freivalds. There is no Fiat–Shamir variant.

## Prior work

Slalom (Tramèr and Boneh, ICLR 2019) delegates the linear layers of a network from a trusted enclave to an untrusted GPU, building on an outsourcing scheme for matrix multiplication, with 6 to 20 times higher throughput on VGG16, MobileNet and ResNet variants (abstract). This folder differs in four ways:
- the model is a language model;
- the arithmetic is exact, one hash on seven machines (`../exact-llm`);
- the check runs on a laptop;
- every count above is measured.

## Files

| File | |
| --- | --- |
| `check.py` | the checker |
| `trace.py` | the prover; `--plain` for the run alone, `--resid` for the leaves of `spot.py`, `--perturb-weight` for the control |
| `spot.py` | commitment, the unit map, single faults, commit and open |
| `run.py` | per batch: plain run, trace, both checks, planted faults |
| `controls.py` | wrong tokens, faulty files, changed weights |
| `reproduce.py` | the one command |
| `test_f64.py` | `exact_mod` against Python integers |
| `estimate.py`, `tally.py` | operation counts from formulas; totals over batches |
| `record/` | every figure above, from one run on the Apple M1 |
| `MANIFEST.sha256` | `shasum -a 256 -c MANIFEST.sha256` |
