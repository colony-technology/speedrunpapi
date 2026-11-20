# speedrunpapi

speedrunpapi, the universal engine: exact results with independent proofs, by [colony.technology](https://colony.technology). For example: output determinism for Circom and R1CS, bounded exact mathematics, bit-exact ONNX plans, audited arithmetic cores, circuit blocks with proofs, exact models.

An under-constrained circuit accepts more than one output for the same input, so the prover decides the result instead of the circuit. `speedrunpapi` checks that property on the constraint system the compiler emits and returns one of three verdicts.

| Verdict | Meaning | Backed by |
| --- | --- | --- |
| `Certified` | Every satisfying witness with the same inputs has the same outputs. | A derivation, replayed by a checker that shares no rule logic with the prover |
| `Broken` | Two satisfying witnesses share every input and differ on an output. | Both witnesses, re-evaluated against every constraint |
| `Unknown` | Neither was established. | The signals that are still open, and why |

A circuit it cannot decide is `Unknown`.

## Quick start

Requires Node.js 20+ and the [circom](https://github.com/iden3/circom/blob/master/mkdocs/docs/getting-started/installation.md) compiler 2.x for `.circom` input.

```sh
npx speedrunpapi scan circuit.circom
```

```text
Broken  examples/division.circom
  claim    Two satisfying witnesses share every input signal and differ on an output signal.
  system   circom 2.2.3 --O0 · 1 constraints · 4 wires · 1 outputs · 2 inputs
  inputs   main.a = 0, main.b = 0
  differs  main.q: 0 vs 1
  checked  both witnesses satisfy all 1 constraints
```

```sh
npm install -g speedrunpapi      # or: pip install speedrunpapi  (same bundle; still needs Node.js)
git clone https://github.com/lmtlssss/speedrunpapi && cd speedrunpapi
speedrunpapi scan examples/iszero.circom examples/decoder.circom examples/modsum-safe.circom
```

Exit status is `0` when every file is `Certified`, `2` if any is `Broken`, `3` if any is `Unknown`, `1` on error. Analysis runs on your machine; nothing is uploaded unless you supply an API key for a signed certificate.

## Usage

```sh
# A circuit with a main component
speedrunpapi scan circuits/withdraw.circom -l node_modules

# A library template: instantiate it as main
speedrunpapi scan node_modules/circomlib/circuits/comparators.circom --main "LessThan(64)" -l node_modules/circomlib/circuits

# A template that expects bits: state the precondition; it is written into the verdict
speedrunpapi scan pedersen.circom --main "Pedersen(248)" --assume-binary in

# An R1CS you already compiled (a sibling .sym supplies signal names)
speedrunpapi scan build/withdraw.r1cs

# Machine-readable result, and the full report for independent checking
speedrunpapi scan circuit.circom --json
speedrunpapi scan circuit.circom --report out/circuit.report.json
speedrunpapi verify out/circuit.report.json --source out/circuit.r1cs
```

| Option | Effect |
| --- | --- |
| `--main "T(args)"` | Instantiate a template as the main component (for library files) |
| `-l, --include <dir>` | circom library directory, repeatable |
| `--assume-binary <pattern>` | Treat matching input signals as bits: `in`, `"sel[*]"`, `"*"` |
| `--strict` | Require every signal, not only outputs, to be fixed by the inputs |
| `--opt O0\|O1\|O2` | Force one circom simplification level (see below) |
| `--report <path>` | Write the full report: derivation or witnesses, plus what it is bound to |
| `--json`, `--full` | JSON summary; `--full` adds the derivation or witnesses |
| `--sarif <file>` | `Broken` results as SARIF for code-scanning dashboards |
| `--timeout`, `--cex-timeout` | Seconds for proof search (600) and counterexample search (15) |
| `--circom <bin>`, `--prime <name>` | Compiler binary and field (`bn128`, `bls12381`, `goldilocks`, ...) |

## What Certified means

`Certified` states output determinism of one constraint system: for any two assignments that satisfy every constraint and agree on all input signals, the output signals agree. With `--strict` the same is stated for every signal.

That a satisfying witness exists, that the circuit computes the intended function and that the inputs stay within their ranges are separate checks.

A circuit with no output signals is never `Certified`: the property says nothing about it. The report then lists the internal signals that are not fixed by the inputs, which is where hint-related bugs live in assert-only circuits.

`--assume-binary` adds the constraint `x * (x - 1) = 0` for each matched input. The verdict holds for callers that pass bits at those inputs. The assumptions are written into the report and the certificate.

### Compiler levels

A verdict about a `.circom` file is a verdict about the R1CS that circom emits for it, under the recorded compiler version and flags.

circom `--O0` applies no simplification, so that system describes the circuit exactly. From `--O1` (circom's default) the compiler merges signals, and an input that equals another signal loses its wire without the `.sym` file recording it; at `--O2` inputs can be substituted by linear combinations. A proof of determinism carries over to every level. A counterexample does not, unless every declared input still has a wire.

`scan` therefore analyses the `--O0` system first and accepts its proof or counterexample. If that is `Unknown` it tries `--O1`, and accepts a counterexample there only when all declared inputs are wired. When you scan an `.r1cs` directly and some declared inputs have no wire, the tool can still certify but will not report `Broken`. Scan the `.circom` source, or an R1CS compiled with `--O0`.

## How it decides

The prover works on the difference of two satisfying assignments that agree on the inputs and shows, wire by wire, that the difference is zero. Rules:

- **lin**: a constraint reduces to a linear equation with constant coefficients in which one wire is not yet determined.
- **fix**: a constraint that mentions a single wire and has a single root.
- **bits**: a linear equation whose undetermined wires are all two-valued, with weights for which the subset-sum map is injective below the modulus. This is the bit-decomposition argument, and it is why `Num2Bits(254)` over BN254 is not certified.
- **gauss**: a linear combination of such equations isolates a wire.
- **onehot**: a selector family. Constraints `s_i * (L - c_i) = C_i` share one determined form `L` and have pairwise distinct constants `c_i`, and a linear equation ties exactly those `s_i` together. At most one factor is zero; every other `s_i` is fixed by its own constraint and the equation fixes the last. This settles `Decoder`-style selectors in one step.
- **split**: case analysis on a determined linear form being zero or nonzero. Both assignments fall in the same case; a wire determined in both cases, or in one while the other is contradictory, is determined. This covers `IsZero` and guarded divisions.

Every rule application is a step in the derivation. The checker re-reads each cited constraint from the R1CS and accepts a step only if its conclusion follows.

For `Broken`, the tool fixes concrete inputs, solves the system by propagation, and looks for a second solution with different outputs, steering inputs toward the degenerate cases the prover could not rule out (a divisor being zero, for example). A pair is reported only after both assignments pass a full evaluation of every constraint.

## Measured

circomlib templates compiled with circom 2.2.3 at `--O0`, analysed on an Apple M1 with Node.js 26. Times are single runs in milliseconds.

| Circuit | Verdict | Constraints | Derivation steps | Prove | Replay |
| --- | --- | ---: | ---: | ---: | ---: |
| `Sha256compression()` | Certified | 202,784 | 192,312 | 228 | 155 |
| `Sha256(64)` | Certified | 204,576 | 194,104 | 252 | 160 |
| `Poseidon(5)` | Certified | 1,347 | 1,347 | 1.9 | 1.1 |
| `MiMCSponge(2, 220, 1)` | Certified | 1,767 | 1,767 | 2.1 | 2.7 |
| Poseidon Merkle root, depth 4 | Certified | 3,102 | 3,098 | 2 | 2 |
| `LessThan(252)` | Certified | 256 | 3 | 0.8 | 0.6 |
| `Multiplexer(2, 4)` | Certified | 36 | 31 | 0.3 | 0.1 |
| `IsZero()` | Certified | 2 | 4 | 0.2 | 0.1 |
| `Num2Bits(254)` | Broken | 255 | | | |
| `Decoder(4)` | Broken | 6 | | | |
| `MontgomeryAdd()` | Broken | 3 | | | |
| `Edwards2Montgomery()` | Broken | 2 | | | |
| `Pedersen(8)`, inputs unrestricted | Broken | 95 (`--O1`) | | | |
| `BabyAdd()` | Unknown | 6 | | | |
| `BabyPbk()` | Unknown | 10,114 | | | |
| `Num2Bits_strict()` | Unknown | 1,285 | | | |

The `Broken` rows are properties of those templates taken alone, with unrestricted inputs. circomlib uses several of them only where the caller rules the degenerate inputs out (`Multiplexer` forces `Decoder`'s `success` to one; Pedersen callers pass bits). The verdict tells you which preconditions your circuit must enforce.

The corpus has 71 circom-compiled cases with known answers. The engine currently decides 61 of them and reports `Unknown` for 10; none of its verdicts contradicts the known answer. A separate fuzzer compares the engine against brute-force enumeration on random systems over small fields (150,000 systems in the release run, no wrong `Certified` or `Broken`).

## What returns Unknown

- Elliptic-curve arithmetic whose uniqueness depends on a number-theoretic fact, such as the completeness of the Baby Jubjub addition law.
- Big-integer arithmetic whose uniqueness depends on range bounds across limbs.
- Alias checks (`Num2Bits_strict`, `AliasCheck`) that compare a bit string against the modulus.
- Circuits with no outputs.
- R1CS with custom gates (PLONK custom templates), or over a field other than the ones circom targets.

For these the report lists each open signal with the condition under which a constraint would fix it, for example `main.xout: fixed by constraint 4 only where (1 + 168696*main.tau) != 0`. Each line gives a condition to check by hand.

## Checking a result yourself

A report is self-contained: the derivation or the two witnesses, the R1CS digest, the compiler and flags, and any assumptions.

```sh
speedrunpapi scan circuit.circom --report circuit.report.json     # also writes circuit.r1cs
speedrunpapi verify circuit.report.json --source circuit.r1cs
python3 "$(npm root -g)/speedrunpapi/verifiers/determinism/determinism_check.py" circuit.r1cs circuit.report.json
```

`verify` uses the JavaScript checker. `determinism_check.py` is a second implementation in Python with no dependencies beyond the standard library and its own R1CS parser. To tie the R1CS back to your source, recompile with the recorded compiler version and flags and compare digests.

## CI

```yaml
- uses: actions/checkout@v4
- uses: lmtlssss/speedrunpapi@v0.7.3
  with:
    file: circuits/main.circom
    include: node_modules/circomlib/circuits
```

The Action installs the pinned circom compiler, scans, uploads the report, and fails on `Broken`. Set `fail_on_unknown: true` to require `Certified`. Supplying `api_key` additionally requests a signed certificate.

## Signed certificates

Local analysis is free. A paid API key adds an Ed25519-signed statement from colony.technology that its service replayed your derivation, or re-evaluated your witness pair, against the R1CS you submitted:

```sh
export COLONY_API_KEY=...
speedrunpapi scan circuit.circom --require-signed
```

The service signs only `Certified` and `Broken` results that it has itself re-verified. The certificate names the R1CS digest, the derivation digest and any assumptions; the source file name and compiler are recorded as client-declared, because the service cannot run your compiler. Uploads are limited to 8 MiB of R1CS; larger circuits are checked locally with `verify` and the Python checker. Certificate status and revocations are public at `api.colony.technology/v1/certificates/status` and `/v1/revocations`.

To check a certificate offline, `node "$(npm root -g)/speedrunpapi/verifiers/cert/verify.mjs" certificate.json circuit.r1cs` (or `node verifiers/cert/verify.mjs …` from a clone of this repository) verifies the Ed25519 signature against the pinned public key and that the certificate names the digest of your file. The signature identifies the issuer. The report lets you re-check the result. Credit packs: [colony.technology/packs](https://colony.technology/packs).

## Earlier versions

Before 0.7.1, sources were classified by template name and keyword. A circuit with unconstrained outputs could receive `Certified`. Certificates issued before 0.7.1 have been revoked. Scan again with 0.7.1 or later. [Release notes](https://github.com/lmtlssss/speedrunpapi/releases).

## Hosted jobs

The hosted-job client (`run`, `solve`, `quote`, `optimize`, `status`, `result`, `check`) and the offline ONNX checker (`verify-onnx`) are described in [docs/hosted-jobs.md](docs/hosted-jobs.md).

## Exact embeddings

[`proofs/exact-embeddings/`](proofs/exact-embeddings/) holds the sentence-embedding model `sentence-transformers/all-MiniLM-L6-v2` computed in integer arithmetic. The 2,758 sentences of the STS-B test set give one SHA-256 on seven machines, x86-64 and ARM64 under Linux, macOS and Windows, where the float32 model and onnxruntime each give six. STS-B Spearman is 0.8203 for all three. The only floating-point operation is a product of integer matrices whose partial sums are bounded below 2^53, and the bound is checked for every weight matrix. [The notebook](https://colab.research.google.com/github/lmtlssss/speedrunpapi/blob/main/proofs/exact-embeddings/exact_embeddings.ipynb) runs it in Colab with NumPy alone.

## Exact language model

[`proofs/exact-llm/`](proofs/exact-llm/) holds the language model `HuggingFaceTB/SmolLM2-135M` computed in integer arithmetic. The logits at the 471 prompt positions of 64 prompts give one SHA-256 on seven machines, where the float32 model gives six and onnxruntime three; the top token equals float32's at 471 of 471 prompt positions. exact-16, in the same folder, makes every operand of every matrix product an integer within ±(2^15 − 1); its three routes, one float64 product, float32 byte products and onnxruntime `MatMulInteger`, print one pair of hashes: 21 runs on seven machines. The same code makes SmolLM2-360M (361,821,120 weights) exact with one pair of hashes on seven machines and three routes, and SmolLM2-1.7B (1,711,376,384 weights) with one pair on six machines, 13 runs; the top token equals float32's at 471 of 471 prompt positions wherever float32 finished.

## Hardware

Logic compilers, netlists and proofs are under [`hardware/`](hardware/).

| EPFL benchmark | Published best | colony |
| --- | --- | --- |
| `voter`, size | 1145 LUT-6 | 987 LUT-6 |
| `voter`, depth | 11 levels | 9 levels |
| `multiplier`, size | 4282 LUT-6 | 3420 LUT-6 |
| `multiplier`, depth | 25 levels | 11 levels |
| `square`, size | 2894 LUT-6 | 2421 LUT-6 |
| `square`, depth | 10 levels, 3690 LUT-6 | 9 levels, 3802 LUT-6 |
| `sqrt`, size | 2958 LUT-6 | 2174 LUT-6 |
| `sqrt`, depth | 150 levels, 45934 LUT-6 | 103 levels, 32337 LUT-6 |
| `hyp`, size | 36451 LUT-6 | 24436 LUT-6 |
| `hyp`, depth | 458 levels, 176274 LUT-6 | 199 levels, 125747 LUT-6 |
| `div`, size | 3082 LUT-6 | 2287 LUT-6 |
| `div`, depth | 170 levels, 30849 LUT-6 | 58 levels, 20232 LUT-6 |
| `sin`, size | 994 LUT-6 | 685 LUT-6 |
| `sin`, depth | 10 levels, 666529 LUT-6 | 10 levels, 360269 LUT-6 |
| `log2`, size | 5986 LUT-6 | 4099 LUT-6 |
| `log2`, depth | 51 levels, 9391 LUT-6 | 23 levels, 7978 LUT-6 |
| `arbiter`, size | 259 LUT-6 | 256 LUT-6 |
| `arbiter`, depth | 5 levels, 369 LUT-6 | 4 levels, 1477 LUT-6 |
| `adder`, depth | 5 levels, 339 LUT-6 | 4 levels, 558 LUT-6 |
| `max`, size | 511 LUT-6 | 510 LUT-6 |
| `max`, depth | 6 levels, 1006 LUT-6 | 6 levels, 868 LUT-6 |
| `dec`, size | 264 LUT-6 | 260 LUT-6 |
| `dec`, depth | 2 levels, 264 LUT-6 | 2 levels, 260 LUT-6 |
| `bar`, size | 512 LUT-6 | 486 LUT-6 |
| `bar`, depth | 4 levels, 512 LUT-6 | 4 levels, 486 LUT-6 |
| `router`, depth | 3 levels, 25 LUT-6 | 3 levels, 22 LUT-6 |
| `cavlc`, depth | 3 levels, 54 LUT-6 | 2 levels, 65 LUT-6 |
| `i2c`, size | 173 LUT-6 | 171 LUT-6 |
| `i2c`, depth | 3 levels, 192 LUT-6 | 2 levels, 323 LUT-6 |
| `mem_ctrl`, size | 1669 LUT-6 | 1666 LUT-6 |
| `mem_ctrl`, depth | 5 levels, 1716 LUT-6 | 5 levels, 1714 LUT-6 |
| `int2float`, depth | 2 levels, 23 LUT-6 | 2 levels, 21 LUT-6 |
| `sixteen`, size | 3282958 LUT-6 | 12691 LUT-6 |
| `twenty`, size | 4166467 LUT-6 | 12719 LUT-6 |
| `twentythree`, size | 470892 LUT-6 | 12744 LUT-6 |
| `sixteen`, depth | 14 levels, 3387001 LUT-6 | 9 levels, 407332 LUT-6 |
| `twenty`, depth | 14 levels, 4381634 LUT-6 | 9 levels, 419071 LUT-6 |
| `twentythree`, depth | 15 levels, 4913996 LUT-6 | 9 levels, 468313 LUT-6 |

[`hardware/epfl-mtm/`](hardware/epfl-mtm/) holds `sixteen`, `twenty` and `twentythree`, the 16 to 23 million gate circuits of the suite. They are the truth table of a Fibonacci loop in 64-bit integers; the netlists compute it, and each is proven equivalent to the original in minutes without a solver.

[`hardware/iwls/`](hardware/iwls/) holds the rules behind twenty functions of the IWLS 2026 contest, which gives them as truth tables only. For ten of them the circuit built from the rule is smaller than the smallest of the twelve teams: 519 to 683 AND nodes where the contest has 2,868 to 8,383, and 1,067 to 2,056 where it has 1,573 to 21,553. [`hardware/iwls/2025/`](hardware/iwls/2025/) does the same for the 2025 contest: the exact rules of twenty-six floating-point functions and eleven circuits smaller than the smallest of the four teams, among them an 8-bit multiplier in 303 AND nodes where the contest has 2,327.

[`hardware/bristol/`](hardware/bristol/) holds sixteen of the Bristol Fashion circuits that garbled-circuit, multi-party computation and zero-knowledge systems load, with fewer AND gates: the IEEE double square root in 2,013 where the published circuit has 91,504, divide in 4,559 where it has 82,269, and the ten float circuits together in 15,704 where they have 204,664. Same file format; they load in place of the published ones. Nine are proved equal to the published ones with ABC, and add, multiply, divide and square root match the arithmetic of the processor on a billion operands each.

[`hardware/epfl-sin/`](hardware/epfl-sin/) holds the EPFL `sin` benchmark as 685 LUT-6 where the smallest published netlist has 994, and the arithmetic the benchmark computes, which the suite does not describe. Both are checked against the benchmark on all 16,777,216 inputs.

[`hardware/epfl-log2/`](hardware/epfl-log2/) holds the EPFL `log2` benchmark as 4,099 LUT-6 where the smallest published netlist has 5,986, a second netlist of 23 levels where the shallowest published has 51, and the arithmetic the benchmark computes, which the suite does not describe. All three are checked against the benchmark on all 4,294,967,296 inputs.

[`hardware/epfl-arbiter/`](hardware/epfl-arbiter/) holds the EPFL round-robin `arbiter` as 256 LUT-6 where the smallest published netlist has 259, with the equations it is built from. ABC proves it equal to the benchmark in under a second.

[`hardware/epfl-depth/`](hardware/epfl-depth/) holds the depth entries for `adder`, `arbiter`, `max`, `square`, `sqrt` and `hyp`, with their checks. [`hardware/epfl-dec/`](hardware/epfl-dec/) holds `dec` at 260 LUT-6 and 2 levels where the best published has 264, proved equal to the benchmark by ABC. The `sin` depth entry is in [`hardware/epfl-sin/`](hardware/epfl-sin/).

[`hardware/epfl-bar/`](hardware/epfl-bar/) holds `bar` at 486 LUT-6 and 4 levels where the best published has 512, proved equal to the benchmark by ABC.

[`hardware/epfl-max/`](hardware/epfl-max/) holds `max` for the size table at 510 LUT-6 where the best published has 511, proved equal to the benchmark by ABC.

[`hardware/epfl-router/`](hardware/epfl-router/) holds `router` for the depth table at 22 LUT-6 and 3 levels, the minimum, where the best published has 25, proved equal to the benchmark by ABC.

[`hardware/epfl-cavlc/`](hardware/epfl-cavlc/) holds `cavlc` for the depth table at 2 levels, the minimum, and 65 LUT-6, where the best published has 3 levels: every output built as one LUT-6 over at most six first-level LUT-6s, found by SAT, then shaved at 2 levels; each output is compared with the benchmark on every input, and ABC proves the whole netlist equal as well.

[`hardware/epfl-i2c/`](hardware/epfl-i2c/) holds `i2c` for the depth table at 2 levels, the minimum, and 323 LUT-6, where the best published has 3 levels, and for the size table at 171 LUT-6, where the best published has 173. Each of the 142 outputs of both netlists is compared with the benchmark on every setting of the inputs it can reach, and ABC proves the whole netlists equal as well.

[`hardware/epfl-mem_ctrl/`](hardware/epfl-mem_ctrl/) holds `mem_ctrl` at 1666 LUT-6 and 27 levels for the size table and 1714 LUT-6 and 5 levels for the depth table, where the best published have 1669 and 1716: the published netlists of F.-X. Reichl and F. Slivovsky with LUTs removed, proved equal to the benchmark by ABC.

[`hardware/epfl-int2float/`](hardware/epfl-int2float/) holds `int2float` for the depth table at 21 LUT-6 and 2 levels, the minimum, where the best published has 23: the published netlist of F.-X. Reichl and F. Slivovsky with two LUTs removed, each output compared with the benchmark on every input, and ABC proves the whole netlist equal as well.

[`hardware/epfl-ties/`](hardware/epfl-ties/) proves three published entries optimal, so they cannot be beaten: `ctrl` at 25 LUT-6 and 2 levels on both tables, and `adder` at 129 LUT-6 and 126 levels on the size table.

[`hardware/divider/udiv.v`](hardware/divider/) is a drop-in unsigned divider: 4,889 cells at 64 bits on Lattice ECP5, placed and routed, where the Verilog operators take 12,246.
`udivf64.v` in the same directory divides in 181 ns on that device, where the operators take 394 ns.
[`hardware/linear/`](hardware/linear/) builds XOR logic: CRC-32 over a 512-bit bus in 701 LUT-6 at 4 levels, where Yosys takes 2,344; with any number of valid bytes, 1,172.
[`hardware/linear/taxi/`](hardware/linear/taxi/) holds CRC-32 modules for the taxi Ethernet MACs. Alex Forencich built them into taxi's MACs on his HTG9200 design (Virtex UltraScale+ VU9P, 60 MACs): about 83 LUTs saved per channel on the 64-bit datapath, 4.7 per MAC on the 32-bit one.

[`hardware/evidence/crc32/`](hardware/evidence/crc32/) holds the Ethernet and ARINC 664 frame check sequence at 8, 32 and 64 bits per clock and 64 bits with byte enables, 41, 100, 151 and 348 LUT-6, as verification evidence for a DO-254 or ISO 26262 applicant. Each block is proven equal to the bit-serial definition on every input by an independent checker and again in Yosys, simulated on 1,000,776 vectors, and replayed on 53 known-answer messages.

[`hardware/evidence/crc32-selfcheck/`](hardware/evidence/crc32-selfcheck/) holds the 64-bit CRC-32 block, unchanged at 151 LUT-6, with a detector of 22 LUT-6 beside it, 173 in all, where duplicate and compare takes 323. Linear algebra and one SAT proof per fault (604 net faults, and every pin fault and INIT bit, 10,583 in all) show that no single fault in the block changes its output without the alarm, on any input. The 8- and 32-bit blocks the same way: 41 and 100 LUT-6 with 15 and 14 more, where duplicate and compare takes 103 and 221.

[`hardware/evidence/secded/`](hardware/evidence/secded/) holds the encoder, syndrome generator and corrector of the (72, 64) and (39, 32) Hsiao codes of OpenTitan's `prim_secded`: the (72, 64) encoder in 31 LUT-6 where the OpenTitan RTL takes 59, the decoder in 120 where it takes 151. For every data word, every flipped bit is corrected and every pair of flipped bits is flagged, proven by linear algebra with the corrector checked on every input, and again by SAT on the whole chain.

[`hardware/evidence/mul-selfcheck/`](hardware/evidence/mul-selfcheck/) holds an unsigned multiplier in LUT-6 at 8, 16, 32 and 64 bits with a detector beside it that compares the remainders of the operands and of the product modulo 3: 136 lookup tables beside the 6,299 of the 64-bit multiplier, where a second multiplier and a comparison take 6,384. An independent checker proves for every input that one wrong table of the multiplier that changes the product raises the alarm; SAT at 8 bits and fault simulation at every width agree, and three negative controls each escape as they should.

[`hardware/evidence/mac-selfcheck/`](hardware/evidence/mac-selfcheck/) does the same for an unsigned multiply-accumulate a × b + c, with one more residue: for m = 3 the detector is 206 tables as built beside the 6,139 of the multiply-accumulate at N = 64, where a second multiply-accumulate and a comparison would cost 6,210.

[`hardware/certificate/hardfloat/`](hardware/certificate/hardfloat/) holds a certificate for the rounding module of Berkeley HardFloat Release 1, `roundRawFNToRecFN` with options 0: the IEEE 754-2019 value and the overflow, underflow and inexact flags for every valid finite nonzero raw input. The whole module is proved by machine at 135 formats, binary16, binary32, binary64, binary128 and x87 extended among them, and every input of 17 small formats is compared with exact rational arithmetic, 3,297,497,088 inputs with 0 differences.

[`hardware/audit/`](hardware/audit/) runs open arithmetic cores beside exact arithmetic: a double-precision divider in dawsonjon/fpu returns 2^29 times the quotient for a band of subnormal results. The floating-point adder of BaseJump STL returns the smallest normal number for 0 + 0. The floating-point unit of OpenHW's CVA5 never answers 0.0 / 2.0 when that division directly follows another one. NOEL-V, Gaisler's RISC-V processor, returns 1.65e-24 for 3.0 * 5.0 - 15.0 at the target of a mispredicted branch. The float package of the VHDL standard, as the IEEE publishes it and GHDL and NVC ship it, returns -15 for (-6)(-1) + (-5) and the wrong last bit for the square root of two in double precision; the patch beside it passes 32 million calls. Two fixes are merged upstream: neorv32 #1692 and black-parrot #1380.
Every netlist has an independent checker; the division and square-root recurrences are proved in Lean 4.

One unit of work, 1,800 USD, fixed, in three forms, each with its own refund: [a core or IP block audited](hardware/audit/#your-block), refunded if no defect is found; [an arithmetic block in your flow](hardware/multiplier/#paid-evaluation), refunded if it does not beat your reference on LUT count or logic depth; [a model made exact](proofs/exact-llm/#your-model), up to 500 million parameters, refunded if two of your machines print different hashes. Larger work, by contract: lmtlssss@colony.technology.

[Terms](https://colony.technology/terms) · [Releases](https://github.com/lmtlssss/speedrunpapi/releases)
Questions: lmtlssss@colony.technology
