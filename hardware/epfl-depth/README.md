# EPFL depth entries

Six entries for the depth table of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks) (`best_results/README.md`). On that table, fewer levels wins, then fewer LUTs.

| Benchmark | Best published, LUT-6 / levels | Here, LUT-6 / levels | Netlist |
| --- | --- | --- | --- |
| `adder` | 339 / 5 | 558 / 4 | [`adder_depth_2027.blif`](adder_depth_2027.blif) |
| `arbiter` | 369 / 5 | 1477 / 4 | [`arbiter_depth_2027.blif`](arbiter_depth_2027.blif) |
| `max` | 1006 / 6 | 868 / 6 | [`max_depth_2027.blif`](max_depth_2027.blif) |
| `square` | 3690 / 10 | 3802 / 9 | [`square_depth_2027.blif`](square_depth_2027.blif) |
| `sqrt` | 45934 / 150 | 32337 / 103 | [`sqrt_depth_2027.blif.gz`](sqrt_depth_2027.blif.gz) |
| `hyp` | 176274 / 458 | 125747 / 199 | [`hyp_depth_2027.blif.gz`](hyp_depth_2027.blif.gz) |

Counts are ABC `read_blif FILE; print_stats`, `nd` and `lev`.

An output of `adder` and of `arbiter` depends on 256 inputs, and a LUT-6 reads 6. Three levels reach at most 6 × 6 × 6 = 216 inputs, so 4 levels is the least possible for both.

The suite's files are those of lsils/benchmarks commit `82d8cc6` (`arithmetic/`, `random_control/`). Python 3 is needed; ABC is `yosys-abc`.

## adder, arbiter, max

Each is equal to the suite's circuit on every input, by ABC:

```
yosys-abc -c "read_blif adder_depth_2027.blif; print_stats; cec -n arithmetic/adder.blif adder_depth_2027.blif"
yosys-abc -c "read_blif arbiter_depth_2027.blif; print_stats; cec -n random_control/arbiter.blif arbiter_depth_2027.blif"
yosys-abc -c "read_blif max_depth_2027.blif; print_stats; cec -n arithmetic/max.blif max_depth_2027.blif"
```

```
adder   : i/o =  256/  129  nd =   558  lev = 4    Networks are equivalent.
arbiter : i/o =  256/  129  nd =  1477  lev = 4    Networks are equivalent.
max     : i/o =  512/  130  nd =   868  lev = 6    Networks are equivalent.
```

## square

The proof is [`independent_depth_checker.py`](independent_depth_checker.py), the checker of [`../multiplier/`](../multiplier/). It reads the netlist and the wire names in [`square_depth_2027.derivation.json`](square_depth_2027.derivation.json). It proves the counter heap equal to `a * a` as a polynomial identity read from the netlist, and the final adder equal to a ripple adder by ABC `cec`. It needs [`independent_mul_checker.py`](independent_mul_checker.py) beside it.

```
python3 independent_depth_checker.py --netlist square_depth_2027.blif --derivation square_depth_2027.derivation.json --abc yosys-abc
```

```
{"levels": 9, "lut_count": 3802, "n": 64, "ok": true, "proof": "heap polynomial identity mod 2^width from the netlist + ABC cec of the final adder against a ripple adder", "square": true}
```

[`simcmp.py`](simcmp.py) also compares it with the suite's `square.blif` (it reads [`blif_sim.py`](blif_sim.py)):

```
python3 simcmp.py arithmetic/square.blif square_depth_2027.blif --words 16 --lengths
{"vectors": 65536, "mismatching_words": 0}
```

A direct ABC `cec` against `square.blif` did not finish within 30 minutes.

## sqrt and hyp

The proof is [`psqrt_check.py`](psqrt_check.py). It reads a netlist and the wire names in its derivation and replays every stage from the netlist; it needs [`hyp_check.py`](hyp_check.py) and `independent_mul_checker.py` beside it.

It runs on the netlist that keeps every wire the derivation names (`*_depth_replayed.blif`). The entry is that netlist with its unused LUTs removed, and ABC proves the two equal.

```
gunzip -k sqrt_depth_replayed.blif.gz sqrt_depth_2027.blif.gz
python3 psqrt_check.py --netlist sqrt_depth_replayed.blif --derivation sqrt_depth.derivation.json --abc yosys-abc
yosys-abc -c "cec -n sqrt_depth_replayed.blif sqrt_depth_2027.blif"
gunzip -k hyp_depth_replayed.blif.gz hyp_depth_2027.blif.gz
python3 psqrt_check.py --netlist hyp_depth_replayed.blif --derivation hyp_depth.derivation.json --abc yosys-abc
yosys-abc -c "cec -n hyp_depth_replayed.blif hyp_depth_2027.blif"
```

```
{"ok": true, "kind": "sqrt", "m": 64, "lut_count": 37228, "levels": 103}       14 s
Networks are equivalent after structural hashing.
{"ok": true, "kind": "hyp", "m": 128, "lut_count": 144066, "levels": 199}      49 s
Networks are equivalent after structural hashing.
```

Against the suite's files, by simulation:

```
for s in 5 6 7 8; do python3 simcmp.py arithmetic/sqrt.blif sqrt_depth_2027.blif --words 4 --lengths --seed $s; done
python3 edge_test.py sqrt_depth_2027.blif 64 arithmetic/sqrt.blif
for s in 22 23 24; do python3 simcmp.py arithmetic/hyp.blif hyp_depth_2027.blif --words 2 --lengths --seed $s; done
```

```
sqrt: 4 x 16,384 = 65,536 vectors, 0 mismatching; 17,429 edge vectors, 0 wrong
hyp:  3 x 8,192 = 24,576 vectors, 0 mismatching
```

No complete equivalence check against the suite's `sqrt.blif` or `hyp.blif` was run. The proof is the replay above, and the comparisons are tests.

## Files

`MANIFEST.sha256` lists every file here with its SHA-256.
