# EPFL max, size

`max` is the four-input maximum of the [EPFL combinational benchmark suite](https://github.com/lsils/benchmarks): four 128-bit words in, the largest and its 2-bit index out, 512 inputs and 130 outputs. This page is its entry for the size table; the depth entry is in [`../epfl-depth/`](../epfl-depth/).

| | LUT-6 | Levels |
| --- | --- | --- |
| Best published, size table (H. Wang and P. Wang, `max_size_2024.blif`) | 511 | 134 |
| [`max_size_2027.blif`](max_size_2027.blif) | 510 | 130 |

The counts are `nd` and `lev` from ABC `print_stats`. The netlist has no constant nodes and no buffers, so these are also the table's numbers. The table's own count, [`../epfl-dec/lutcount.py`](../epfl-dec/lutcount.py), gives 510 / 130 for this netlist and 511 / 134 for `best_results/size/max_size_2024.blif`.

## Check

[`check.py`](check.py) compares the netlist with the suite's `arithmetic/max.blif` on 36,864 vectors, every output by name: 16 x 2,048 random vectors plus the all-zero and all-one vectors. It then counts the netlist with ABC and runs ABC `cec` against the benchmark. It needs Python 3 and reads [`blifkit.py`](blifkit.py); ABC is `yosys-abc`, or set `ABC`.

```
python3 check.py arithmetic/max.blif max_size_2027.blif --cec-seconds 50
```

```
simulation: 36864 vectors, 0 batches with a mismatch
print_stats:  i/o = 512/ 130 lat = 0 nd = 510 edge = 2681 cube = 10256 lev = 130
cec: ['Networks are equivalent.  Time =     1.05 sec']
```

The suite's file is from lsils/benchmarks commit `3e9df8b`.
