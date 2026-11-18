# EPFL i2c, depth

`i2c` is the I2C controller of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 147 inputs, 142 outputs. This page is its entry for the depth table. On that table fewer levels wins, then fewer LUTs.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, depth table (A. Tempia Calvino et al., `i2c_depth_2026.blif`) | 192 | 3 |
| [`i2c_depth_2027.blif`](i2c_depth_2027.blif) | 508 | 2 |

Two levels is the minimum: `po028` depends on 24 inputs and one LUT-6 reads 6. So the level count cannot go lower, and what is left open on this entry is the number of LUTs at 2 levels.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 508 / 2 for this netlist and 192 / 3 for `best_results/depth/i2c_depth_2026.blif`. ABC's `nd` is 523 because it also counts 14 outputs that are a wire or an inverter of one input and 1 constant output. ABC's `lev` is 2 here as well: no output sits behind more than two nodes of any kind.

## How it was made

Every output is built on its own, from its function and not from the suite's gates.

- 1 output is constant and 14 are one input or its inverse.
- 27 depend on 2 to 6 inputs and are one LUT each.
- 100 depend on 7 to 24 inputs. Each is one LUT-6 over at most six first-level LUT-6s, `f = T(g1, ..., g6)`, every `g` reading at most 6 inputs.

For 97 of those 100 the six `g` were found by a SAT search, [`two_level.py`](two_level.py). The search is told, for every `g` and every input, whether `g` reads that input, and for every input row what `g` gives; a `g` that does not read an input must give the same value on the two rows that differ only there. Before the search, inputs that the output sees only through one AND or one OR are grouped and treated as a single input that costs as many LUT pins as it has members. That shrinks an output of 21 inputs to about 8.

For `po015`, `po040` and `po043` the search did not finish, and the split was written by hand from the output's own formula. Each of the three is a small set of cases chosen by a few control inputs, with a different expression over the other inputs in each case. Two or three of the six `g` say which case holds; the others carry the expressions, and the same `g` is reused across cases that cannot hold together. `po015`, for example, with `a = pi003 + pi129`, `q = pi005 + pi022`, `r = pi009 + pi011`:

```
pi054 = 0:               po015 = a + pi000
pi054 = 1, q or r:       po015 = a + q r + pi056
pi054 = 1, q = r = 0:    po015 = a + OR(pi004, pi006, pi012, pi016, pi017, pi018, pi019)
                                   + OR(pi000, pi008, pi010, pi013, pi014, pi021)
                                     AND (the number of ones among pi007, pi008, pi010, pi013, pi014, pi021 is not 1)
```

The first-level LUTs that are equal between outputs are kept once: 381 first-level LUTs, 100 second-level LUTs and 27 single LUTs, 508 in all.

## Check

[`prove.py`](prove.py) compares the netlist with the suite's `random_control/i2c.blif` without ABC. For each output it takes every input that either netlist can reach from that output, at most 24, and compares the two on all settings of those inputs. That decides each output completely. It needs Python 3 and numpy and takes about a minute.

```
python3 prove.py random_control/i2c.blif i2c_depth_2027.blif
```

```
nodes by number of inputs: {0: 1, 1: 14, 2: 40, 3: 104, 4: 55, 5: 53, 6: 256}
LUTs with 2 or more inputs: 508
levels, every node counted: 2
levels, nodes with 2 or more inputs counted: 2
142 outputs, each compared on every setting of the inputs it can reach (at most 24 inputs, 130437033 settings in all): 0 outputs differ
PROVED EQUAL
```

[`check.py`](check.py) is the check of [`../epfl-router/`](../epfl-router/): 36,864 vectors by simulation, every output by name, then ABC's count and ABC `cec` against the benchmark. It reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/i2c.blif i2c_depth_2027.blif --cec-seconds 100
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 147/ 142 lat = 0 nd = 523 edge = 2427 cube = 10807 lev = 2
cec: ['Networks are equivalent.  Time =     0.18 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif i2c_depth_2027.blif; strash; cec -n random_control/i2c.aig"
Networks are equivalent.  Time =     0.17 sec
```

The suite's files are from lsils/benchmarks commit `82d8cc6`.
