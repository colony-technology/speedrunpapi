# EPFL cavlc, depth

`cavlc` is the CAVLC decoder of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 10 inputs, 11 outputs. This page is its entry for the depth table. On that table fewer levels wins, then fewer LUTs.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, depth table (`cavlc_depth_2026.blif`) | 54 | 3 |
| [`cavlc_depth_2027.blif`](cavlc_depth_2027.blif) | 53 | 3 |

The table counts LUTs with two or more inputs and the levels over those, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py): 53 / 3 for this netlist and 54 / 3 for `best_results/depth/cavlc_depth_2026.blif`.

## How it was made

The netlist is the published one with one LUT removed. [`resub2.py`](resub2.py) rebuilds a node over at most six other signals of the netlist and drops the old node when every node that read it is rebuilt; the kept change is the `new-node` move at `new_n16`, which drops one LUT at 3 levels.

The circuit has 10 inputs, so signals are compared on a sample of input patterns and a rebuilt node can be wrong. Every kept change is therefore checked on the whole netlist with ABC `cec` against the suite circuit before it is kept. A refused change gives a counterexample, which joins the sample. The netlist is equal to the suite circuit after every kept change.

```
python3 resub2.py cavlc best_results/depth/cavlc_depth_2026.blif OUT.blif
```

It needs numpy, python-sat and ABC (`yosys-abc`, or set `ABC`), and the suite's `random_control/` (or set `EPFL_SUITE`). The search is sampled, so another run may reach a different netlist at the same count; the shipped netlist is the one proven below.

## Check

[`prove.py`](prove.py) compares the netlist with the suite's `random_control/cavlc.blif` on every input, output by output, without ABC. It needs Python 3 and numpy.

```
python3 prove.py random_control/cavlc.blif cavlc_depth_2027.blif
```

```
nodes by number of inputs: {6: 53}
LUTs with 2 or more inputs: 53
levels, every node counted: 3
levels, nodes with 2 or more inputs counted: 3
11 outputs, each compared on every setting of the inputs it can reach (at most 10 inputs, 10496 settings in all): 0 outputs differ
PROVED EQUAL
```

[`check.py`](check.py) is the check of [`../epfl-router/`](../epfl-router/): 36,864 vectors by simulation, every output by name, then ABC's count and ABC `cec` against the benchmark. It reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py random_control/cavlc.blif cavlc_depth_2027.blif --cec-seconds 60
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 10/ 11 lat = 0 nd = 53 edge = 318 cube = 626 lev = 3
cec: ['Networks are equivalent.  Time =     0.03 sec']
```

Against the AIG as well:

```
yosys-abc -c "read_blif cavlc_depth_2027.blif; strash; cec -n random_control/cavlc.aig"
Networks are equivalent.  Time =     0.03 sec
```

The suite's files are from lsils/benchmarks commit `82d8cc6`.
