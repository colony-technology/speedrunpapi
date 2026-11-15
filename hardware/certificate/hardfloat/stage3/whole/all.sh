#!/bin/zsh
# all.sh: step 1b. The whole roundRawFNToRecFN against spec_gen.py at every documented format with
# w = 3..8 (p = 3 .. 2^(w-2)+3: 132 formats, binary16 and binary32 among them), then binary64 (11, 53),
# x87 extended (15, 64) and binary128 (15, 113). 900 s limit per format. Then the two planted faults.
# Log: whole.txt.
cd "$(dirname "$0")" || exit 2
Y=${EDA_BIN:-$(dirname "$(command -v yosys)")}/yosys
: > whole.txt
$Y -V >> whole.txt
for W in 3 4 5 6 7 8; do
  for P in $(seq 3 $(( (1 << (W - 2)) + 3 ))); do ./one.sh $W $P 900 >> whole.txt; done
done
for WP in "11 53" "15 64" "15 113"; do ./one.sh ${=WP} 900 >> whole.txt; done
RAW=$(pwd)/../../work/mutant/HardFloat_rawFN.v TAG=mutant_ ./one.sh 4 5 900 >> whole.txt
SPEC=spec_gen_mut.py TAG=specmut_ ./one_s.sh 4 5 900 >> whole.txt
echo "done $(date '+%H:%M:%S')" >> whole.txt
