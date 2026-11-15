#!/bin/zsh
# all.sh: one.sh for every p = 3..113 (binary16 p 11, binary32 24, binary64 53, binary128 113 among them),
# then the two broken copies at a few widths. Each width has its own 600 s limit. Log: formal.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
cd $HERE || exit 2
Y=${EDA_BIN:-$(dirname "$(command -v yosys)")}/yosys
: > formal.txt
$Y -V >> formal.txt
for P in {3..113}; do ./one.sh $P 600 >> formal.txt; done
for P in 3 11 24 53 113; do DESC=../hf_datapath_broken.bv TAG=broken_ ./one.sh $P 600 >> formal.txt; done
for P in 3 11 24 53 113; do DESC=../hf_datapath_broken2.bv TAG=broken2_ ./one.sh $P 600 >> formal.txt; done
echo "done $(date '+%H:%M:%S')" >> formal.txt
