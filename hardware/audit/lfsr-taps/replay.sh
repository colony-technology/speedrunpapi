#!/bin/sh
# Replays this audit. Prints each check and ends with one line: PASSED or FAILED.
#   sh replay.sh      needs Python 3.9 or later (standard library only) and, for the last step, Verilator.
# About 6 to 9 minutes, most of it the Chisel table. Writes only to a temporary directory.
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
W=$(mktemp -d "${TMPDIR:-/tmp}/lfsr-taps.XXXXXX") || exit 1
fails=0
ran=0

# expect DESCRIPTION EXIT PATTERN -- command ...: passes when the command exits with EXIT and its output has PATTERN
expect() {
  desc=$1; want=$2; pat=$3; shift 4
  out=$("$@" 2>&1); got=$?
  ran=$((ran + 1))
  if [ "$got" = "$want" ] && printf '%s\n' "$out" | grep -q -- "$pat"; then
    echo "ok    $desc"
  else
    echo "FAIL  $desc (exit $got, wanted $want and \"$pat\")"
    printf '%s\n' "$out" | tail -n 5 | sed 's/^/      /'
    fails=$((fails + 1))
  fi
}

echo "== 1. Self-test of the arithmetic"
expect "primality routines: no wrong answer on 25 known numbers" 0 "wrong \[\]" -- $PY -I selftest.py
expect "GF(2) routines and the factorisations of 2^n - 1 at the large widths" 0 "2^4096 - 1: 25 distinct primes, verified" -- $PY -I selftest.py

echo "== 2. The four tables and the control"
$PY -I audit_taps.py data "$W/out" control cc ot chisel > "$W/audit.log" 2>&1
for t in control common_cells opentitan chisel; do
  want=$(sed 's/; [0-9.]* s$//' "results/$t.txt")
  got=$(sed 's/; [0-9.]* s$//' "$W/out/$t.txt" 2>/dev/null)
  ran=$((ran + 1))
  if [ -n "$got" ] && [ "$got" = "$want" ]; then echo "ok    $want"; else echo "FAIL  $t: got \"$got\", recorded \"$want\""; fails=$((fails + 1)); fi
done

echo "== 3. The finding: every state of cc_lfsr_16bit, as shipped and fixed"
expect "as shipped: cycles of 64,897, 511, 127 and 1" 0 "as shipped, taps 15, 12, 5, 1: 4 cycles, lengths \[64897, 511, 127, 1\]" -- $PY -I finding-cc_lfsr_16bit/cycles.py
expect "fixed: one cycle of 65,535 and the lockup state" 0 "fixed, taps 15, 14, 12, 3: 2 cycles, lengths \[65535, 1\]" -- $PY -I finding-cc_lfsr_16bit/cycles.py

if command -v verilator >/dev/null 2>&1; then
  echo "== 4. The shipped file in Verilator, and the one-line fix"
  cp finding-cc_lfsr_16bit/rtl/cc_lfsr_16bit.sv "$W/orig.sv"
  sed 's/shift_in = !(shift_q\[15\] ^ shift_q\[12\] ^ shift_q\[5\] ^ shift_q\[1\]);/shift_in = !(shift_q[15] ^ shift_q[14] ^ shift_q[12] ^ shift_q[3]);/' \
    finding-cc_lfsr_16bit/rtl/cc_lfsr_16bit.sv > "$W/fixed.sv"
  for v in orig fixed; do
    verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style -Ifinding-cc_lfsr_16bit/rtl/include --top-module tb_period \
      -Mdir "$W/v_$v" -o sim "$W/$v.sv" finding-cc_lfsr_16bit/tb_period.sv > "$W/v_$v.log" 2>&1
  done
  expect "as shipped, from the default seed: period 64,897" 0 "period from seed 0000: 64897" -- "$W/v_orig/sim"
  expect "with the fix: period 65,535" 0 "period from seed 0000: 65535" -- "$W/v_fixed/sim"
else
  echo "== 4. Verilator: skipped, not on the path"
fi

rm -rf "$W"
if [ "$fails" = 0 ]; then
  echo "PASSED ($ran checks)"
else
  echo "FAILED ($fails of $ran checks)"
  exit 1
fi
