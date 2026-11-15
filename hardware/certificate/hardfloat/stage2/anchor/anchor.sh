#!/bin/zsh
# anchor.sh: HardFloat's internal datapath signals against hf_datapath.bv, w = 5, p = 3..9 (all formats
# HardFloat documents for w = 5 up to p = 9), every valid finite nonzero input. Writes anchor.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
HF=${HARDFLOAT:?set HARDFLOAT to the unpacked HardFloat-1 directory}/source
OSS=${EDA_BIN:-$(dirname "$(command -v verilator)")}
cd $HERE || exit 2
: > anchor.txt
for P in 3 4 5 6 7 8 9; do
  $OSS/verilator --cc --exe --build -j 1 -O2 --public-flat-rw -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH \
    -GW=5 -GP=$P -CFLAGS "-O2 -DTB_W=5 -DTB_P=$P" --top-module tb --Mdir obj_p$P -o anchor \
    +incdir+$HF +incdir+$HF/RISCV $HF/HardFloat_primitives.v $HF/HardFloat_rawFN.v ../../stage1/tb.v $HERE/anchor.cpp \
    > obj_p$P.build.txt 2>&1 || { echo "build failed p=$P" >> anchor.txt; continue; }
  obj_p$P/anchor > dump_p$P.txt
  python3 -I anchor_check.py ../hf_datapath.bv $P dump_p$P.txt >> anchor.txt
done
