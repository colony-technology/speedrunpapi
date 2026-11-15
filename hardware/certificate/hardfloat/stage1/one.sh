#!/bin/zsh
# one.sh W P : reference table, Verilator build and exhaustive comparison for one format.
# Output: logs/wW_pP.log (last line is the count line of harness.cpp).
set -u
W=$1; P=$2
HERE=$(cd "$(dirname "$0")" && pwd)
HF=${HARDFLOAT:?set HARDFLOAT to the unpacked HardFloat-1 directory}/source
RAW=${RAW:-$HF/HardFloat_rawFN.v}; TAG=${TAG:-}
OSS=${EDA_BIN:-$(dirname "$(command -v verilator)")}
cd $HERE || exit 2
mkdir -p tables obj logs
LOG=logs/${TAG}w${W}_p${P}.log
{
  echo "== $(date '+%H:%M:%S') ref.py $W $P"
  python3 -I $HERE/ref.py $W $P tables/w${W}_p${P}.bin
  echo "== $(date '+%H:%M:%S') verilator"
  $OSS/verilator --cc --exe --build -j 1 -O2 --x-assign 0 --x-initial 0 -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH \
    -GW=$W -GP=$P -CFLAGS "-O2 -DTB_W=$W -DTB_P=$P" --top-module tb --Mdir obj/${TAG}w${W}_p${P} -o sim \
    +incdir+$HF +incdir+$HF/RISCV $HF/HardFloat_primitives.v $RAW $HERE/tb.v $HERE/harness.cpp \
    > obj/${TAG}w${W}_p${P}.build.txt 2>&1 || { echo "verilator failed"; tail -20 obj/${TAG}w${W}_p${P}.build.txt; exit 3; }
  echo "== $(date '+%H:%M:%S') sim"
  obj/${TAG}w${W}_p${P}/sim tables/w${W}_p${P}.bin
  echo "== $(date '+%H:%M:%S') end"
} > $LOG 2>&1
tail -1 $LOG | grep -v '^==' ; grep '^w=' $LOG | tail -1
