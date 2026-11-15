"""Reads a SEC-DED parity-check matrix from an OpenTitan decoder (as text) and checks it.

    python3 tools/matrix.py --source source/prim_secded_72_64_dec.sv --out proof/H_72_64.json

H is r x n: row i is the mask of syndrome_o[i] (bits 0..k-1 data, k..n-1 check).  Printed and checked:
  every column non-zero, all n columns distinct, every column of odd weight      (the SEC-DED conditions)
  check columns are the r unit vectors (systematic code)
  column weights, row weights, total weight                                       (the Hsiao conditions)
  the decoder's correction table: data_o[j] is flipped exactly at syndrome = column j
"""
import argparse
import json
import re
from pathlib import Path

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    text = a.source.read_text()
    found = [(int(m.group(1)), int(m.group(2)), int(m.group(3), 16))
             for m in re.finditer(r"syndrome_o\[(\d+)\] = \^\(data_i & (\d+)'h([0-9A-Fa-f]+)\)", text)]
    n = found[0][1]
    rows = {i: v for i, _, v in found}
    r = len(rows)
    k = n - r
    assert sorted(rows) == list(range(r)) and all(w == n for _, w, _ in found)
    col = [sum(((rows[i] >> j) & 1) << i for i in range(r)) for j in range(n)]
    table = {int(m.group(1)): int(m.group(2), 16) for m in re.finditer(r"data_o\[(\d+)\]\s*= \(syndrome_o == \d+'h([0-9A-Fa-f]+)\) \^ data_i\[\d+\]", text)}
    pc = lambda x: bin(x).count("1")
    res = {
        "source": "lowRISC/opentitan hw/ip/prim/rtl/" + a.source.name, "n": n, "k": k, "r": r,
        "rows": ["%x" % rows[i] for i in range(r)],
        "columns": ["%x" % c for c in col],
        "nonzero": all(col), "distinct": len(set(col)) == n, "odd_weight": all(pc(c) & 1 for c in col),
        "check_columns_unit": [col[k + i] for i in range(r)] == [1 << i for i in range(r)],
        "data_column_weights": {str(w): sum(1 for c in col[:k] if pc(c) == w) for w in sorted(set(pc(c) for c in col[:k]))},
        "row_weights": [pc(rows[i]) for i in range(r)], "total_weight": sum(pc(rows[i]) for i in range(r)),
        "decoder_table_matches_columns": sorted(table) == list(range(k)) and all(table[j] == col[j] for j in range(k)),
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print("(%d, %d), %d check bits" % (n, k, r))
    for key in ("nonzero", "distinct", "odd_weight", "check_columns_unit", "data_column_weights", "row_weights", "total_weight", "decoder_table_matches_columns"):
        print("%-30s %s" % (key, res[key]))
    raise SystemExit(0 if res["nonzero"] and res["distinct"] and res["odd_weight"] and res["check_columns_unit"] and res["decoder_table_matches_columns"] else 1)
