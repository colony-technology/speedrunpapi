# EPFL cavlc, depth

`cavlc` is the CAVLC decoder of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 10 inputs, 11 outputs. This page is its entry for the depth table. On that table fewer levels wins, then fewer LUTs.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, depth table (`cavlc_depth_2026.blif`) | 54 | 3 |
| [`cavlc_depth_2027.blif`](cavlc_depth_2027.blif) | 65 | 2 |

Two levels is the minimum: nine of the eleven outputs depend on all 10 inputs and one LUT-6 reads 6. The netlist below reaches 2 levels for every output.

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 65 / 2 for this netlist and 54 / 3 for `best_results/depth/cavlc_depth_2026.blif`.

## How it was made

Each output is built on its own, as one LUT-6 over at most six first-level LUT-6s, `f = T(g1, ..., g6)`, every `g` reading at most 6 inputs.

For every output the six `g` and the top table were found by SAT, [`tl2.py`](tl2.py). The search is told, for every `g` and every input, whether `g` reads that input, and for every input row what `g` gives; a `g` that does not read an input must give the same value on the two rows that differ only there. Every answer is verified against the truth table on all 1,024 inputs before it is kept. Ten outputs answered SAT in seconds to hours; output 6 needed 11,762 s of kissat.

```
python3 tl2.py tt/cavlc.npy 0 --kissat /path/to/kissat --seed 1 --budget 20000 --save res_o0.json
```

[`assemble_tl2.py`](assemble_tl2.py) then puts the eleven decompositions together, sharing first-level LUTs that are identical, and checks every output against the truth table on all inputs. That gives 77 LUT-6 at 2 levels: 66 first-level LUTs and 11 top LUTs.

```
python3 assemble_tl2.py tt/cavlc.npy random_control/cavlc.blif OUT.blif RESULT_DIR
```

[`resub2.py`](resub2.py) then removes LUTs at 2 levels, down to 65. It drops a LUT when every LUT that reads it can be rebuilt without it, over at most six other signals taken from the whole netlist, and a rebuilt LUT may only read signals that keep every output at 2 levels. Signals are compared on a sample of input patterns, so every kept change is checked on the whole netlist with ABC `cec` against the suite circuit before it is kept; a refused change gives a counterexample, which joins the sample.

```
python3 resub2.py cavlc START.blif OUT.blif --levels 2
```

It needs numpy, python-sat and ABC (`yosys-abc`, or set `ABC`), and the suite's `random_control/` (or set `EPFL_SUITE`).

## Check

[`prove.py`](prove.py) compares the netlist with the suite's `random_control/cavlc.blif` on every input, output by output, without ABC. It needs Python 3 and numpy.

```
python3 prove.py random_control/cavlc.blif cavlc_depth_2027.blif
```

```
nodes by number of inputs: {5: 1, 6: 64}
LUTs with 2 or more inputs: 65
levels, every node counted: 2
levels, nodes with 2 or more inputs counted: 2
11 outputs, each compared on every setting of the inputs it can reach (at most 10 inputs, 9984 settings in all): 0 outputs differ
PROVED EQUAL
```

[`check.py`](check.py) is the check of [`../epfl-router/`](../epfl-router/): 36,864 vectors by simulation, every output by name, then ABC's count and ABC `cec` against the benchmark. It reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/cavlc.blif cavlc_depth_2027.blif --cec-seconds 60
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 10/ 11 lat = 0 nd = 65 edge = 389 cube = 1824 lev = 2
cec: ['Networks are equivalent.  Time =     0.04 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif cavlc_depth_2027.blif; strash; cec -n random_control/cavlc.aig"
Networks are equivalent.  Time =     0.04 sec
```

The suite's files are from lsils/benchmarks commit `82d8cc6`.
