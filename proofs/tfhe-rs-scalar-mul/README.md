# TFHE-rs scalar multiplication in signed digits

[zama-ai/tfhe-rs](https://github.com/zama-ai/tfhe-rs) multiplies an encrypted integer by a known integer in `ServerKey::unchecked_scalar_mul_assign_parallelized` (`tfhe/src/integer/server_key/radix_parallel/scalar_mul.rs`). It writes the known integer in binary and adds one shifted copy of the ciphertext for every set bit. `scalar_mul_naf.patch` writes it in non-adjacent form instead, digits -1, 0 and +1 with no two non-zero digits side by side, so a run of ones costs two terms. A -1 digit adds the bitwise NOT of the shifted copy, which costs no bootstrap, and one clear constant at the end corrects the sum. The patch keeps the binary path whenever the signed form would not give fewer terms.

Measured on tfhe-rs `b07e249c925bad47b03ed2bc93a99c2b6feaaad7`, the head of `main` on 15 November 2026, on a hosted GitHub Actions runner (ubuntu-latest, 2 threads) on 15 November 2026. Parameters `PARAM_MESSAGE_2_CARRY_2_KS_PBS`. The counter is the library's own `pbs-stats` feature (`tfhe::reset_pbs_count`, `tfhe::get_pbs_count`). Both trees see the same 200 random scalars and 10 edge scalars per width (splitmix64, seed 20261115), each multiplied into a fresh encryption of a random value.

Bootstraps (PBS) per scalar multiplication, 200 random scalars per width:

| width | binary mean | signed mean | change | binary worst | signed worst | binary ms | signed ms |
|---|---|---|---|---|---|---|---|
| 16 | 40.1 | 34.4 | -14.2 % | 56 | 46 | 1172.9 | 1002.4 |
| 32 | 128.6 | 105.0 | -18.4 % | 181 | 135 | 3722.0 | 3044.4 |
| 64 | 424.2 | 327.1 | -22.9 % | 563 | 385 | 12221.5 | 9407.5 |

Every product was decrypted and compared with the product computed in the clear: 630 of 630 right on each tree.

The scalar with every bit set falls from 63 to 16 bootstraps at 16 bits, from 212 to 32 at 32 bits and from 767 to 64 at 64 bits. The other nine edge scalars cost the same on both trees: 0, 1, 2, 3, two powers of two, 0b1011, alternating bits, and two ones at the top.

On the patched tree, 12 tests were run and all 12 passed. Eleven are the library's own: unchecked and default scalar multiplication at the 1_1, 2_2 and 3_3 parameter sets, signed scalar multiplication, the u128 regression test, and unsigned and signed scalar division. The twelfth is added by the patch. It checks for every 12-bit value that the digits give back the value and that no two non-zero digits touch.

## The count before the run

`tfhe_scalar_mul_count.py` is a model of the library's scalar multiplication on plain integers, and `predict_ci_scalars.py` counts the same scalars with it. The counts above were taken on 2 threads. The model was first run for 4 threads, the expected size of the runner, and gave -10.1, -16.0 and -21.1 percent; on a 4-thread machine those are the changes to expect. The thread count changes how the library propagates carries, so it changes the count. Run for 2 threads, the model gives every edge count, mean and worst in the table above exactly.

```
python3 -I -B predict_ci_scalars.py 200 20261115 2
```

## Not measured

- The GPU backend. `backends/tfhe-cuda-backend/cuda/src/integer/scalar_mul.cuh` decomposes the scalar into the same binary digits; the patch does not touch it.
- Benchmarks on a quiet, dedicated machine. The milliseconds come from a shared hosted runner with 2 threads.
- Parameter sets other than 2_2. The 1_1 and 3_3 sets were run only in the unit tests, for correctness.

## Run it

From a clean checkout of tfhe-rs, with the toolchain its `rust-toolchain.toml` names:

```
git clone https://github.com/zama-ai/tfhe-rs
cd tfhe-rs
git checkout b07e249c925bad47b03ed2bc93a99c2b6feaaad7
cp ../tfhe-rs-scalar-mul/naf_scalar_mul_count.rs tfhe/examples/

NAF_LABEL=unpatched NAF_SAMPLES=200 NAF_SEED=20261115 cargo run --profile release_lto_off \
  -p tfhe --example naf_scalar_mul_count --features=integer,pbs-stats

git apply ../tfhe-rs-scalar-mul/scalar_mul_naf.patch

NAF_LABEL=patched NAF_SAMPLES=200 NAF_SEED=20261115 cargo run --profile release_lto_off \
  -p tfhe --example naf_scalar_mul_count --features=integer,pbs-stats
```

Each run prints one line per case and ends with the summary table. The unit tests, with the exact filters, are the last step of `naf-scalar-mul.yml`, the workflow that produced `logs/`.

## Files

| file | |
|---|---|
| `scalar_mul_naf.patch` | the change, applied with `git apply` from the tfhe-rs root; it touches only `scalar_mul.rs` |
| `naf_scalar_mul_count.rs` | the counting example, public API only, the same file on both trees |
| `naf-scalar-mul.yml` | the GitHub Actions workflow: both trees, then the unit tests |
| `logs/unpatched.log`, `logs/patched.log` | every case and the summary, as printed |
| `logs/unit_tests.log`, `logs/unit_tests_list.txt` | the 12 selected tests and their result |
| `tfhe_scalar_mul_count.py`, `predict_ci_scalars.py` | the model and the prediction |
| `LICENSE-tfhe-rs` | the tfhe-rs licence |
| `MANIFEST.sha256` | SHA-256 of every file here |

In the logs the runner's checkout directory is shortened to `/home/runner/work/<repository>/<repository>`; nothing else in the logs was changed.

## Licence

The patch carries lines of tfhe-rs source, which is BSD-3-Clause-Clear, copyright Zama (`LICENSE-tfhe-rs`). The patch is offered under that licence.
