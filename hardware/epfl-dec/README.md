# EPFL dec

`dec` is the 8-to-256 decoder of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks), random/control half: 8 inputs, 256 outputs. The suite keeps the best known LUT-6 results in two tables, by size and by depth.

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, size and depth tables (L. Machado and J. Cortadella) | 264 | 2 |
| [`dec_size_2027.blif`](dec_size_2027.blif) | 260 | 2 |
| [`dec_depth_2027.blif`](dec_depth_2027.blif), the same netlist | 260 | 2 |

Two levels is the minimum: every output depends on all 8 inputs, and a LUT-6 reads 6. So the depth entry is decided by LUTs at 2 levels.

The table counts LUTs with two or more inputs and the levels over those. This netlist has no LUT with fewer than two inputs, so ABC's `nd` and `lev` are the table's numbers.

## Proof

Against `random_control/dec.aig` and `random_control/dec.blif` of lsils/benchmarks commit `3e9df8b`:

```
yosys-abc -c "read dec_size_2027.blif; print_stats; cec -n dec.aig; cec -n dec.blif"
```

```
dec : i/o = 8/ 256  lat = 0  nd = 260  edge = 1560  cube = 385  lev = 2
Networks are equivalent.
Networks are equivalent.
```

[`check.py`](check.py) evaluates both circuits on all 256 input rows and compares every output, matched by name. It needs Python 3 with NumPy and reads [`aig.py`](aig.py).

```
python3 check.py dec.aig dec_size_2027.blif
```

```
inputs 8, rows 256, outputs 256, matched by name
rows that differ from the reference: 0
LUTs with >= 2 inputs: 260; levels over those: 2; largest LUT: 6 inputs
```

[`lutcount.py`](lutcount.py) gives the count the table uses:

```
python3 lutcount.py dec_size_2027.blif
table count: LUTs(>=2 inputs) 260  levels 2  max fanin 6
```

`dec_depth_2027.blif` is byte for byte `dec_size_2027.blif`.
