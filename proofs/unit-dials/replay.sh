#!/usr/bin/env bash
# replay.sh : every table of README.md from the sources here. Needs python3, a C compiler (cc), Yosys with yosys-abc,
# and Icarus Verilog (iverilog, vvp). Work goes to build/. Exit 0 when every check holds.
#   1. the statements, the oldest form, the searches and the cheap sets: equal to record/, line for line
#   2. the shipped netlists (netlists/, mapped by Yosys 0.70+385): exhaustive simulation against the definitions,
#      0 mismatches; the 15-bit binary adder and multiplier by ABC cec; both negative controls must fail
#   3. the cost tables again with the local Yosys: printed beside record/cost_table.md (counts depend on the version)
set -u
cd "$(dirname "$0")" || exit 2
HERE=$(pwd); B=$HERE/build; rm -rf "$B"; mkdir -p "$B"
ok=0; bad=0
check() { if [ "$1" = 0 ]; then echo "ok    $2"; ok=$((ok+1)); else echo "FAIL  $2"; bad=$((bad+1)); fi; }
same() { diff -q "$1" "$2" > /dev/null; check $? "$3"; }
python3 -V; cc --version 2>&1 | head -1; yosys -V; iverilog -V 2>&1 | head -1

echo "== 1. statements, searches"
python3 -I src/check_claims.py 1000 300 60 > "$B/claims.txt"; same "$B/claims.txt" record/claims.txt "claims 1-4 and the three lines (record/claims.txt)"
python3 -I src/oldest.py > "$B/oldest.txt"; same "$B/oldest.txt" record/oldest.txt "the signed sums of unit fractions (record/oldest.txt)"
cc -O2 -o "$B/search4" src/search4.c && cc -O2 -o "$B/search5" src/search5.c; check $? "compile search4.c, search5.c"
"$B/search4" 2000 4 > "$B/four.txt" 2> /dev/null; same "$B/four.txt" record/four.txt "four dials below 2,000, ratio <= 4: 549 sets (record/four.txt)"
"$B/search5" 600 4 > "$B/five.txt" 2> /dev/null; same "$B/five.txt" record/five.txt "five dials below 600, ratio <= 4: 52 sets (record/five.txt)"
(cd "$B" && python3 -I "$HERE/src/analyse.py" four.txt 4 > analyse4.txt && python3 -I "$HERE/src/analyse.py" five.txt 5 > analyse5.txt)
same "$B/analyse4.txt" record/analyse4.txt "four dials: signs, most balanced, cheap, factor criterion (record/analyse4.txt)"
same "$B/analyse5.txt" record/analyse5.txt "five dials: signs, most balanced, cheap (record/analyse5.txt)"
python3 -I src/cheap4.py 40 4 > "$B/cheap.txt"; same "$B/cheap.txt" record/cheap.txt "cheap moduli, k <= 40, ratio <= 4 (record/cheap.txt)"

echo "== 2. the shipped netlists against their definitions"
for S in s5_8_13 s7_9_32 s15_17_128 s7_8_9 s15_16_17; do
  bash src/prove_sim.sh "netlists/$S" "$B/sim/$S" > "$B/sim_$S.txt" 2>&1
  n=$(grep -c 'mismatches' "$B/sim_$S.txt"); z=$(grep -c 'mismatches 0$' "$B/sim_$S.txt")
  [ "$n" -gt 0 ] && [ "$n" = "$z" ]; check $? "$S: $z of $n modules, 0 mismatches on every valid input"
done
bash src/prove_sim.sh netlists/control "$B/sim/control" 2>&1 | grep '^back' > "$B/sim_control.txt"
grep -q 'mismatches [1-9]' "$B/sim_control.txt"; check $? "control, (5, 8, 13) reading back with 65 -> 66 must mismatch: $(cat "$B/sim_control.txt")"
C=$B/cec; mkdir -p "$C"
for op in add mul; do
  sym='+'; [ $op = mul ] && sym='*'
  echo "module bin$op(input [14:0] a, input [14:0] b, output [14:0] y); assign y = a $sym b; endmodule" > "$C/bin$op.v"
  yosys -q -p "read_verilog $C/bin$op.v; synth -flatten -top bin$op; aigmap; write_aiger -zinit $C/bin$op.gold.aig" > /dev/null 2>&1
  yosys -q -p "read_verilog netlists/s15_17_128/bin$op.lut.v; hierarchy -top gate; techmap; opt -fast; aigmap; rename gate bin$op; write_aiger -zinit $C/bin$op.gate.aig" > /dev/null 2>&1
  yosys-abc -c "cec $C/bin$op.gold.aig $C/bin$op.gate.aig" > "$C/bin$op.cec.txt" 2>&1
  grep -q 'Networks are equivalent' "$C/bin$op.cec.txt"; check $? "15-bit bin$op of (15, 17, 128) against a $sym b, ABC cec"
done
echo "module binmul(input [14:0] a, input [14:0] b, output [14:0] y); assign y = (a * b) ^ 15'd1; endmodule" > "$C/bad.v"
yosys -q -p "read_verilog $C/bad.v; synth -flatten -top binmul; aigmap; write_aiger -zinit $C/bad.gold.aig" > /dev/null 2>&1
yosys-abc -c "cec $C/bad.gold.aig $C/binmul.gate.aig" > "$C/bad.cec.txt" 2>&1
grep -q 'NOT EQUIVALENT' "$C/bad.cec.txt"; check $? "control, cec against (a * b) ^ 1 must fail"

echo "== 3. cost with the local Yosys"
: > "$B/cost.txt"
for S in "5 8 13" "7 9 32" "15 17 128" "7 8 9" "15 16 17"; do
  D=$B/cost/s${S// /_}
  python3 -I src/gen_cost.py "$D" $S >> "$B/cost.txt"
  bash src/map.sh "$D" >> "$B/cost.txt"
done
python3 -I src/cost_table.py "$B/cost.txt" > "$B/cost_table.md"
if diff -q "$B/cost_table.md" record/cost_table.md > /dev/null; then echo "same  cost tables as record/cost_table.md"
else echo "note  cost tables differ from record/cost_table.md (Yosys version): diff build/cost_table.md record/cost_table.md"; fi

echo "== $ok ok, $bad failed"
[ "$bad" = 0 ]
