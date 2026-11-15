#!/usr/bin/env bash
# replay.sh DATA_DIR : every table of README.md from the public record. Needs Python 3 with NumPy (set PYTHON,
# default python3) and network access to zenodo.org. Work goes to build/. Exit 0 when every check holds.
#   1. the 24 DataExp.mat tree files of Zenodo 10534905, fetched by HTTP range out of Experiments.zip into
#      DATA_DIR (21 MB; files already there with the right size are kept), checked against record/data.sha256
#   2. the two controls on drawn forks, every reading of the record, and the thin-channel reckoning:
#      equal to record/, line for line
# The downloaded files are read as data. Nothing in DATA_DIR is run.
set -u
[ $# -eq 1 ] || { echo "usage: bash replay.sh DATA_DIR" >&2; exit 2; }
mkdir -p "$1" && DATA=$(cd "$1" && pwd) || exit 2
cd "$(dirname "$0")" || exit 2
HERE=$(pwd); B=$HERE/build; rm -rf "$B"; mkdir -p "$B"
PY=${PYTHON:-python3}
URL=https://zenodo.org/api/records/10534905/files/Experiments.zip/content
ok=0; bad=0
check() { if [ "$1" = 0 ]; then echo "ok    $2"; ok=$((ok+1)); else echo "FAIL  $2"; bad=$((bad+1)); fi; }
same() { diff -q "$B/$1" "record/$1" > /dev/null; check $? "$2 (record/$1)"; }
if command -v sha256sum > /dev/null; then SHA="sha256sum"; else SHA="shasum -a 256"; fi
"$PY" -I -c "import sys, numpy; print('Python', sys.version.split()[0], 'NumPy', numpy.__version__)" || exit 2
start=$(date +%s)

echo "== 1. the record"
"$PY" -I src/zipget.py "$URL" get DataExp.mat "$DATA" > "$B/download.txt"; check $? "fetch DataExp.mat members of Experiments.zip"
n=$(ls "$DATA" | grep -c 'DataExp\.mat$'); [ "$n" = 24 ]; check $? "$n tree files in DATA_DIR"
(cd "$DATA" && $SHA -c "$HERE/record/data.sha256" > "$B/data.check.txt" 2>&1); check $? "SHA-256 of the 24 files (record/data.sha256)"

echo "== 2. controls and readings"
"$PY" -I src/forks3d.py --control > "$B/control.txt"; same control.txt "reader control: drawn forks of 43, 60, 72, 90, straight and bent back"
"$PY" -I src/forks3d.py "$DATA" "$B/forks3d.tsv" > "$B/forks3d.txt"; same forks3d.txt "2,643 discharges, 728 forks"
same forks3d.tsv "the 728 forks, one line each"
"$PY" -I src/forks3d_profile.py "$DATA" > "$B/profile.txt"; same profile.txt "opening by stretch of path, 689 forks"
"$PY" -I src/forks3d_cond.py "$DATA" > "$B/cond.txt"; same cond.txt "opening by stretch, by condition"
"$PY" -I src/forks3d_where.py "$DATA" > "$B/where.txt"; same where.txt "closing by place in the gap, by condition"
"$PY" -I src/forks3d_balance.py "$DATA" > "$B/balance.txt"; same balance.txt "closing and opening against place, diameter, speed"
"$PY" -I src/forks3d_ride.py "$DATA" > "$B/ride.txt"; same ride.txt "closing against opening over distance left to the plate"
"$PY" -I src/forks3d_birth.py "$DATA" > "$B/birth.txt"; same birth.txt "carry-back at the measured 0.87"
"$PY" -I src/forks3d_scan.py "$DATA" > "$B/scan.txt"; same scan.txt "birth angle: scan of p, bootstrap, by condition and place"
"$PY" -I src/forks3d_line.py "$DATA" > "$B/line.txt"; same line.txt "birth angle by a straight line through each fork's openings"
"$PY" -I src/forks3d_line2.py "$DATA" > "$B/line2.txt"; same line2.txt "the two ways and the two stored fork points"
"$PY" -I src/forks3d_scan_control.py > "$B/scan_control.txt"; same scan_control.txt "scan control: drawn birth angles 60, 72, 85 under five closing rules, both ways"
"$PY" -I src/fork3d_theory.py > "$B/theory.txt"; same theory.txt "thin channels in three dimensions: closed form, opening that holds by kappa"
"$PY" -I src/heat_fork.py "$DATA" > "$B/heat-fork.txt"; same heat-fork.txt "three legs: charges per length read from the turns, against stored thickness and speed"
"$PY" -I src/heat_kernel.py "$DATA" > "$B/heat-kernel.txt"; same heat-kernel.txt "three legs forward: thicknesses in, opening and turns out"

echo "== $ok ok, $bad failed, $(( $(date +%s) - start )) s"
[ "$bad" = 0 ]
