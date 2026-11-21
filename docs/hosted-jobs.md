# Hosted jobs and offline checkers

This page carries the documentation of the hosted-job client and the ONNX checker as published with 0.6.4. They are unchanged in 0.7.1. In 0.7.2 only the missing-key message and the first line of `colony-jobs` help changed. The circuit scanner described in the main README is separate from these commands.

## Hosted jobs

`speedrunpapi` includes a public client for colony's hosted optimization and proof service. Set `COLONY_API_KEY` to an active, funded customer key. The same commands work from the npm and Python packages. The source is sent to the hosted API only when you run a hosted command.

```sh
export COLONY_API_KEY="your-customer-key"
speedrunpapi quote model.onnx
speedrunpapi optimize model.onnx --out optimized.onnx --proof-dir evidence
speedrunpapi verify-onnx evidence/source.onnx evidence/artifacts
```

`optimize` returns an executable ONNX model and its source-bound proof artifacts. `verify-onnx` runs the independent checker locally, without the API, the private optimizer or an API key. Install the checker dependencies with `python3 -m pip install 'onnx>=1.16,<2' 'numpy>=1.26,<3'`. For the Python distribution use `pip install 'speedrunpapi[onnx]'`. The CPU timing evidence is a measured observation on the stated host; each exact stage proof checks model behavior under its declared semantics.

For other supported exact problems, use `speedrunpapi run problem.math`, `speedrunpapi solve problem.math`, `speedrunpapi status <job-id>`, `speedrunpapi result <job-id>` and `speedrunpapi check source.file result.json`. `speedrunpapi jobs <command>` and the `colony-jobs` executable expose the same hosted interface. Requests consume credits only when the service accepts and settles a funded job. The hosted API is [api.colony.technology](https://api.colony.technology).

### Exact mathematical jobs (R15)

Nineteen bounded exact operators are registered. They implement source-specific operators from the M-01 through M-14 mathematical papers, four foundational contracts and the chain operator. Each `.math` source names the exact operator and its input domain. The separate CLI checker reconstructs the original mathematics and rejects modified evidence even when its digest is recalculated. Unsupported parameters return `Unknown`.

M-05 adds complete cascaded sum/carry responses. M-07 and M-08 supply the 35-rectangle nonnegative tensor certificate and a 20-term signed tensor algorithm. M-09 checks the sparse GF(2) operators. M-10 determines the cyclic occupancy energy minimum. M-11 selects exact rational lattice phases. M-12 classifies recurrence horizons. M-13 computes transported affine-cycle defects. M-14 composes exact quadratic costs under the ᑕ. observation contract. Each implementation states its bounded inputs in the returned scope; the full research theorems are cited separately.

`chain.ordered-decision.v1` decides whether an ordered decision list, x0 op0 (x1 op1 ( ... x[N-1])) with each op OR or AND, is computed by a network of k-input tables of at most a declared depth. The source gives `k` (2 to 8), `depth` (1 to 4) and the list, either as `kinds`, run lengths beginning with an OR run, or as `alternating: N`; the list has 2 to 256 variables, and the kind of the last variable has no effect. A `Built` result carries every table with its inputs and its 2^k-bit truth table, primary inputs named by position, the network depth and table count, and the sub-list each table computes. The checker evaluates every table on all 2^k rows. It checks every composition step against the identities F_S(R) = F_S(0) OR (P_S AND R) and F_S(R) = F_S(1) AND (E_S OR R), where P_S is the AND of the AND-variables and E_S the OR of the OR-variables of segment S, and the rule that the last wire may hold units of one kind around units of the other around the bottom item. It checks that the segments partition the list in order, and it simulates the network on every input when N is at most 20. It needs no key and no solver. A modified table, a swapped position or a recalculated digest is rejected. When no network of the declared depth is available the result is `Unknown`, which does not state that none exists.

The production result examples for M-02, M-03, M-04, M-05 and M-06 through M-14 can be independently replayed offline with:

```sh
speedrunpapi check examples/m02-tap-span.math examples/m02-tap-span.result.json
speedrunpapi check examples/m03-affine-inverse.math examples/m03-affine-inverse.result.json
speedrunpapi check examples/m04-two-stage.math examples/m04-two-stage.result.json
speedrunpapi check examples/m06-shared-input.math examples/m06-shared-input.result.json
speedrunpapi check examples/m05-cascade.math examples/m05-cascade.result.json
speedrunpapi check examples/m07-rank35.math examples/m07-rank35.result.json
speedrunpapi check examples/m08-signed20.math examples/m08-signed20.result.json
speedrunpapi check examples/m09-binary-word.math examples/m09-binary-word.result.json
speedrunpapi check examples/m10-cyclic-energy.math examples/m10-cyclic-energy.result.json
speedrunpapi check examples/m11-lattice-phase.math examples/m11-lattice-phase.result.json
speedrunpapi check examples/m12-damped-horizon.math examples/m12-damped-horizon.result.json
speedrunpapi check examples/m13-affine-cycle.math examples/m13-affine-cycle.result.json
speedrunpapi check examples/m14-taa-cost.math examples/m14-taa-cost.result.json
```

These result bundles came from funded technical-test jobs in production. They carry original source digests and exact independent mathematical evidence. They do not represent external card payments. New hosted jobs require an API key with credits.

The chain operator examples: alternating lists of 12 variables at k = 4, depth 2, of 26 at k = 6, depth 2, and of 120 at k = 6, depth 3; and the lists of bits 6 down to 2 of a 128-input priority encoder, each variable one input or its complement, written as runs of 64, 32, 16, 8 and 4, at k = 6, depth 3. These bundles were produced by the operator implementation before hosting and are not records of funded jobs.

```sh
for name in alt12-k4 alt26-k6 alt120-k6 prio6-k6 prio5-k6 prio4-k6 prio3-k6 prio2-k6; do
  speedrunpapi check examples/m15-chain-$name.math examples/m15-chain-$name.result.json
done
```

A [replayable production ONNX proof](proofs/hosted-onnx-production-20261110/) accompanies this release. The source, candidate, cost decision, transformation proof and independent checker are available to inspect. Local scans remain free and offline.

## Portable ᑕ. proof demonstration

[Exact carry-state contraction, 4,096 → 6 retained states](proofs/carry-frontier-4096/) is a complete portable evidence packet. It preserves the declared high-result observations of six modular additions for **all admissible lower-prefix inputs and every high suffix**. The 682.7× factor describes the reduction in retained states, not a CPU speedup.

The original source, mathematical candidate, separate verifier source, exact input/claim digests and Ed25519 laboratory receipt travel together. A reviewer can run the independent checker with Python 3.11 and Node 20+, from a clone of this repository:

`python3 proofs/carry-frontier-4096/verifier/verify.py`

This mathematical reproduction requires no colony account, private optimizer, or network access. Its Ed25519 key is generated per run; it is not a colony certificate. The [proof workflow](.github/workflows/portable-proof.yml) replays it on GitHub Actions.
