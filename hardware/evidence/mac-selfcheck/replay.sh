#!/bin/sh
# Replays the evidence of this folder. Prints each check and ends with one line: PASSED or FAILED.
#
#   sh replay.sh            Python checks (under a minute); then, if found on the path:
#                           cc        -> fault simulation at N = 4 and 16 (seconds)
#                           yosys-abc -> SAT at N = 4 (minutes)
#                           yosys     -> the size measurement (a few minutes)
#   sh replay.sh --no-sat   the same without the SAT step
#
# Needs Python 3.9 or later, standard library only. Writes only to a temporary directory.
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
W=$(mktemp -d "${TMPDIR:-/tmp}/mac-selfcheck.XXXXXX") || exit 1
NOSAT=0
[ "$1" = "--no-sat" ] && NOSAT=1
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

echo "== 1. The checker, every N, m = 3 and m = 15"
for n in 4 5 6 8 16 32 64; do
  expect "N = $n, m = 3: claim A" 0 "PROVED claim A: N = $n, m = 3" -- \
    $PY -I proof/check_selfcheck_mac.py netlists/scm${n}_m3 netlists/mac$n/law.json
  expect "N = $n, m = 15: claims A and B" 0 "PROVED claim B: N = $n, m = 15" -- \
    $PY -I proof/check_selfcheck_mac.py netlists/scm${n}_m15 netlists/mac$n/law.json --claim-b
done

echo "== 2. Negative controls, Python"
for n in 4 5 6 8 16 32 64; do
  expect "N = $n: claim B with m = 3 is refused" 2 "NOT PROVED claim B: N = $n, m = 3" -- \
    $PY -I proof/check_selfcheck_mac.py netlists/scm${n}_m3 netlists/mac$n/law.json --claim-b
done
expect "detector without the wire above the top is refused" 1 "alarm does not read" -- \
  $PY -I proof/check_selfcheck_mac.py netlists/controls/scm4_m3_notop netlists/mac4/law.json
expect "the multiply-accumulate at N = 4 is right on all 65,536 inputs" 0 "65536 inputs simulated, 0 wrong" -- \
  $PY -I proof/macsim.py netlists/mac4
expect "cell correct only on the rows that occur: right without a fault" 0 "65536 inputs simulated, 0 wrong" -- \
  $PY -I proof/macsim.py netlists/controls/mac4_c3
expect "cell correct only on the rows that occur: lawcheck_mac.py refuses it" 1 "FAILED: cell 10" -- \
  $PY -I proof/lawcheck_mac.py netlists/controls/mac4_c3
expect "cell correct only on the rows that occur: the checker refuses it" 1 "NOT PROVED" -- \
  $PY -I proof/check_selfcheck_mac.py netlists/controls/scm4_c3_m3 netlists/controls/mac4_c3/law.json
expect "cell correct only on the rows that occur: rebuilt, with its escape" 0 '"residues": \[0, 0\]' -- \
  $PY -I proof/control3_mac.py netlists/mac4 "$W/c3"
expect "  the rebuilt control is the one in netlists/controls" 0 "" -- cmp "$W/c3/mul.blif" netlists/controls/mac4_c3/mul.blif

echo "== 3. The detector rebuilt from its generator (N = 4) and the cell shapes"
for m in 3 15; do
  expect "N = 4, m = $m: generator output" 0 "detector" -- $PY -I proof/gen_detector_mac.py netlists/mac4 $m "$W/scm4_m$m"
  for f in selfcheck.blif detector.blif det.json; do
    expect "  $f identical" 0 "" -- cmp "$W/scm4_m$m/$f" netlists/scm4_m$m/$f
  done
done
expect "cell shapes: 22, at most 3 outputs, B at most 7" 0 "shapes: 22; largest number of outputs: 3; largest B: 7" -- \
  $PY -I proof/shapes_mac.py netlists/mac4 netlists/mac5 netlists/mac6 netlists/mac8 netlists/mac16 netlists/mac32 netlists/mac64

if command -v cc >/dev/null 2>&1; then
  echo "== 4. Fault simulation (cc found)"
  expect "N = 4, m = 3, every table: 0 escapes" 0 "escapes: 0\." -- \
    $PY -I tools/fsim_mac.py netlists/scm4_m3 netlists/mac4/law.json table3 "$W/f4"
  expect "N = 16, m = 15, every cell: 0 escapes" 0 "escapes: 0\." -- \
    $PY -I tools/fsim_mac.py netlists/scm16_m15 netlists/mac16/law.json cell "$W/f16"
  expect "control, no wire above the top: 84 escapes" 0 "escapes: 84\." -- \
    $PY -I tools/fsim_mac.py netlists/controls/scm4_m3_notop netlists/mac4/law.json table3 "$W/f4n"
else
  echo "== 4. Fault simulation: skipped, no cc on the path"
fi

if [ "$NOSAT" = 0 ] && command -v yosys-abc >/dev/null 2>&1; then
  echo "== 5. SAT at N = 4 (yosys-abc found)"
  expect "m = 3, every table a free input: 54 UNSATISFIABLE" 0 "54 queries, UNSATISFIABLE 54;" -- \
    $PY -I tools/sat_faults_mac.py netlists/scm4_m3 netlists/mac4/law.json tablefree --limit 300 --out "$W/s1.tsv"
  expect "m = 15, every cell's outputs free: 22 UNSATISFIABLE" 0 "22 queries, UNSATISFIABLE 22;" -- \
    $PY -I tools/sat_faults_mac.py netlists/scm4_m15 netlists/mac4/law.json cellfree --limit 300 --out "$W/s2.tsv"
  expect "control, m = 3, whole cells: 21 SATISFIABLE" 0 "SATISFIABLE 21, UNSATISFIABLE 1;" -- \
    $PY -I tools/sat_faults_mac.py netlists/scm4_m3 netlists/mac4/law.json cellfree --limit 300 --out "$W/s3.tsv"
else
  echo "== 5. SAT: skipped (--no-sat, or no yosys-abc on the path)"
fi

if command -v yosys >/dev/null 2>&1; then
  echo "== 6. Size through Yosys (synth; abc -lut 6)"
  expect "detector sizes at N = 4, 8, 16, 32, 64" 0 "N = 64: multiplier 6139 tables" -- \
    $PY -I tools/measure_mac.py netlists "$W/measure.json" 4 8 16 32 64
  [ -f "$W/measure.json" ] && $PY -I -c "import json,sys; r=json.load(open(sys.argv[1])); [print('      N = %s: detector m = 3 %s, m = 15 %s (LUTs, levels)' % (n, v['det_m3'], v['det_m15'])) for n, v in r.items()]" "$W/measure.json"
else
  echo "== 6. Size: skipped, no yosys on the path"
fi

rm -rf "$W"
if [ "$fails" = 0 ]; then
  echo "PASSED ($ran checks)"
else
  echo "FAILED ($fails of $ran checks)"
  exit 1
fi
