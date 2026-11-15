#!/usr/bin/env bash
# replay.sh DATA_DIR : every table of README.md from the public records. Needs Python 3 with NumPy and SciPy (set
# PYTHON, default python3), curl, and network access to zenodo.org and dataverse.nl. Work goes to build/. Exit 0
# when every check holds.
#   1. into DATA_DIR (files already there with the right size are kept), checked against record/data.sha256:
#      the 24 DataExp.mat tree files and the 24 StreamerFinal_in3D.mat detection files of Zenodo 10534905, by
#      HTTP range out of Experiments.zip (21 MB and 104 MB); fig1a.dat of DataverseNL doi:10.34894/MGLPXM
#      (0.6 MB); 21C7-C12sp.dat of Zenodo 7394137, by HTTP range out of AllFigures.zip (9.4 MB)
#   2. every reading of sections 1 to 4 of README.md: equal to record/, line for line
# The downloaded files are read as data. Nothing in DATA_DIR is run.
set -u
[ $# -eq 1 ] || { echo "usage: bash replay.sh DATA_DIR" >&2; exit 2; }
mkdir -p "$1" && DATA=$(cd "$1" && pwd) || exit 2
cd "$(dirname "$0")" || exit 2
HERE=$(pwd); B=$HERE/build; rm -rf "$B"; mkdir -p "$B"
PY=${PYTHON:-python3}
EXP=https://zenodo.org/api/records/10534905/files/Experiments.zip/content
FIG=https://zenodo.org/api/records/7394137/files/AllFigures.zip/content
F1A=https://dataverse.nl/api/access/datafile/93268
C21=Figure2__files__21C7-C12sp.dat
ok=0; bad=0
check() { if [ "$1" = 0 ]; then echo "ok    $2"; ok=$((ok+1)); else echo "FAIL  $2"; bad=$((bad+1)); fi; }
same() { diff -q "$B/$1" "record/$1" > /dev/null; check $? "$2 (record/$1)"; }
if command -v sha256sum > /dev/null; then SHA="sha256sum"; else SHA="shasum -a 256"; fi
"$PY" -I src/versions.py || exit 2
start=$(date +%s)

echo "== 1. the records"
"$PY" -I src/zipget.py "$EXP" get DataExp.mat "$DATA" > "$B/download.txt"; check $? "fetch the DataExp.mat members of Experiments.zip"
"$PY" -I src/zipget.py "$EXP" get StreamerFinal_in3D.mat "$DATA" 20000000 >> "$B/download.txt"; check $? "fetch the StreamerFinal_in3D.mat members of Experiments.zip"
if [ ! -f "$DATA/fig1a.dat" ] || [ "$(wc -c < "$DATA/fig1a.dat" | tr -d ' ')" != 612504 ]; then
  curl -sSfL -A research-script/1.0 -o "$DATA/fig1a.dat" "$F1A"
fi
check $? "fetch fig1a.dat, DataverseNL doi:10.34894/MGLPXM"
"$PY" -I src/zipget.py "$FIG" get 21C7-C12sp.dat "$DATA" >> "$B/download.txt"; check $? "fetch 21C7-C12sp.dat out of AllFigures.zip, Zenodo 7394137"
n=$(ls "$DATA" | grep -c 'DataExp\.mat$'); [ "$n" = 24 ]; check $? "$n tree files in DATA_DIR"
n=$(ls "$DATA" | grep -c 'StreamerFinal_in3D\.mat$'); [ "$n" = 24 ]; check $? "$n detection files in DATA_DIR"
(cd "$DATA" && $SHA -c "$HERE/record/data.sha256" > "$B/data.check.txt" 2>&1); check $? "SHA-256 of the 50 files (record/data.sha256)"

echo "== 2. readings"
"$PY" -I src/triangle2.py "$DATA" > "$B/triangle2.txt"; same triangle2.txt "1. the junction balance: one exponent for both equations, three readings of the turns"
"$PY" -I src/kirchhoff.py "$DATA" > "$B/kirchhoff.txt"; same kirchhoff.txt "2. what the fork conserves, the speed law between sisters"
"$PY" -I src/det_current.py "$DATA" "$DATA" > "$B/det_current.txt"; same det_current.txt "2. the speeds at the junction, from the raw dots"
"$PY" -I src/planes.py "$DATA" > "$B/planes.txt"; same planes.txt "3. the quarter turn, stored planes, 577 pairs, control"
"$PY" -I src/planes_check.py "$DATA" > "$B/planes_check.txt"; same planes_check.txt "3. grouping of the stored forks; planes from other lines"
"$PY" -I src/planes_azimuth.py "$DATA" > "$B/planes_azimuth.txt"; same planes_azimuth.txt "3. the quarter turn against the cameras' axes"
"$PY" -I src/det_planes.py "$DATA" > "$B/det_planes.txt"; same det_planes.txt "3. the quarter turn, raw dots, 752 pairs, control"
"$PY" -I src/det_planes2.py "$DATA" > "$B/det_planes2.txt"; same det_planes2.txt "3. three forks in a row, raw dots"
"$PY" -I src/cloud_planes.py "$DATA/$C21" scholten > "$B/cloud_21c7.txt"; same cloud_21c7.txt "4. lightning, flash 21C-7"
"$PY" -I src/cloud_planes.py "$DATA/fig1a.dat" scholten > "$B/cloud_20a7.txt"; same cloud_20a7.txt "4. lightning, flash 20A-7"

echo "== $ok ok, $bad failed, $(( $(date +%s) - start )) s"
[ "$bad" = 0 ]
