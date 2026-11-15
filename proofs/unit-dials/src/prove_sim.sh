#!/usr/bin/env bash
# prove_sim.sh NETDIR WORKDIR : proof of each mapped netlist NETDIR/<top>.lut.v (Yosys $lut cells, simulated with
# Yosys's simlib.v) against its definition, by Icarus on every valid input. The definitions are written in the
# bench, independent of the generated Verilog:
#   chadd_m, chmul_m   every a, b < m: y = (a + b) mod m, y = (a * b) mod m
#   back               every x in [0, M): the residues (x mod m_i) in, x out (no reconstruction constants)
#   binadd, binmul     every a, b < 2^b when 2b <= 24: y = (a + b) mod 2^b, (a * b) mod 2^b
# NETDIR/spec.json gives the moduli, M and b. Benches and simulations go to WORKDIR.
# Prints one line per module: top, vectors, mismatches.
set -u
NET=$(cd "$1" && pwd)
mkdir -p "$2"; cd "$2" || exit 2
SIMLIB=$(yosys-config --datdir)/simlib.v
MS=$(python3 -I -c "import json, sys; print(*json.load(open(sys.argv[1]))['moduli'])" "$NET/spec.json")
M=$(python3 -I -c "import json, sys; print(json.load(open(sys.argv[1]))['M'])" "$NET/spec.json")
B=$(python3 -I -c "import json, sys; print(json.load(open(sys.argv[1]))['b'])" "$NET/spec.json")
bits() { python3 -I -c "import sys; print(max(1, (int(sys.argv[1]) - 1).bit_length()))" "$1"; }
run() {   # name
  [ -f "$NET/$1.lut.v" ] || return 0
  iverilog -g2012 -o "$1.simv" "$1.tb.v" "$NET/$1.lut.v" "$SIMLIB" > "$1.sim.build" 2>&1 || { echo "$1: build failed: $(grep -m1 -i error "$1.sim.build")"; return; }
  vvp -n "$1.simv" | grep -E '^RESULT' | sed "s/^RESULT/$1:/"
}
for m in $MS; do
  k=$(bits "$m")
  for op in add mul; do
    sym='+'; [ $op = mul ] && sym='*'
    cat > "ch${op}_$m.tb.v" <<EOT
module tb; reg [$((k-1)):0] a, b; wire [$((k-1)):0] y; integer i, j, n, bad;
  gate dut(.a(a), .b(b), .y(y));
  initial begin n = 0; bad = 0;
    for (i = 0; i < $m; i = i + 1) for (j = 0; j < $m; j = j + 1) begin
      a = i; b = j; #1; n = n + 1; if (y !== (i $sym j) % $m) bad = bad + 1; end
    \$display("RESULT vectors %0d mismatches %0d", n, bad); \$finish; end
endmodule
EOT
    run "ch${op}_$m"
  done
done
PORTS=""; DECL=""; ASG=""; i=0
for m in $MS; do k=$(bits "$m"); DECL="$DECL reg [$((k-1)):0] r$i;"; PORTS="$PORTS .r$i(r$i),"; ASG="$ASG r$i = x % $m;"; i=$((i+1)); done
cat > back.tb.v <<EOT
module tb; integer x, n, bad; $DECL wire [$((B-1)):0] y;
  gate dut($PORTS .x(y));
  initial begin n = 0; bad = 0;
    for (x = 0; x < $M; x = x + 1) begin $ASG #1; n = n + 1; if (y !== x) bad = bad + 1; end
    \$display("RESULT vectors %0d mismatches %0d", n, bad); \$finish; end
endmodule
EOT
run back
if [ $((2 * B)) -le 24 ]; then
  for op in add mul; do
    sym='+'; [ $op = mul ] && sym='*'
    cat > "bin$op.tb.v" <<EOT
module tb; reg [$((B-1)):0] a, b; wire [$((B-1)):0] y; integer i, j, n, bad;
  gate dut(.a(a), .b(b), .y(y));
  initial begin n = 0; bad = 0;
    for (i = 0; i < (1 << $B); i = i + 1) for (j = 0; j < (1 << $B); j = j + 1) begin
      a = i; b = j; #1; n = n + 1; if (y !== ((i $sym j) & ((1 << $B) - 1))) bad = bad + 1; end
    \$display("RESULT vectors %0d mismatches %0d", n, bad); \$finish; end
endmodule
EOT
    run "bin$op"
  done
else
  echo "binadd, binmul: 2^$((2*B)) pairs, not simulated (equivalence by ABC cec in replay.sh)"
fi
