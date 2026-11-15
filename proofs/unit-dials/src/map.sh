#!/usr/bin/env bash
# map.sh DIR : map every module DIR/<top>.v written by gen_cost.py to 6-input lookup tables with Yosys
#   synth -flatten; abc -lut 6; opt_clean; stat; ltp -noff
# and write the mapped netlist to DIR/<top>.lut.v. Prints one line per module: top, lookup tables, levels.
set -u
DIR=$1
for f in "$DIR"/*.v; do
  case $f in *.lut.v|*.tb.v) continue;; esac
  top=$(basename "$f" .v)
  yosys -q -l "$DIR/$top.map.log" -p "read_verilog $f; synth -flatten -top $top; abc -lut 6; opt_clean; stat; ltp -noff; rename $top gate; write_verilog -noattr $DIR/$top.lut.v" > /dev/null 2>&1
  luts=$(grep -E '^\s+[0-9]+ +\$lut' "$DIR/$top.map.log" | tail -n 1 | awk '{print $1}')
  [ -z "$luts" ] && luts=$(grep -E '\$lut' "$DIR/$top.map.log" | tail -n 1 | awk '{print $NF}')
  lev=$(grep -o 'length=[0-9]*' "$DIR/$top.map.log" | tail -n 1 | cut -d= -f2)
  echo "$top: ${luts:-none} LUT-6, ${lev:-none} levels"
done
