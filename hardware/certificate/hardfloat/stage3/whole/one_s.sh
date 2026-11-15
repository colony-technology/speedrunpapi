#!/bin/zsh
# one.sh W P [TIMEOUT] : formal equivalence of the whole roundRawFNToRecFN#(W, P) (HardFloat source, unchanged)
# with spec_gen.py's module, under the documented input domain, bits fixed by the documentation only.
# RAW= may name another HardFloat_rawFN.v (a planted fault). Prints: w p result seconds.
set -u
W=$1; P=$2; T=${3:-900}
HERE=$(cd "$(dirname "$0")" && pwd)
HF=${HARDFLOAT:?set HARDFLOAT to the unpacked HardFloat-1 directory}/source
Y=${EDA_BIN:-$(dirname "$(command -v yosys)")}/yosys
RAW=${RAW:-$HF/HardFloat_rawFN.v}; TAG=${TAG:-}
cd $HERE || exit 2
D=${TAG}w${W}_p${P}; mkdir -p $D
python3 -I ../../stage2/bv2v.py ../../stage2/ref_round.bv $((P + 4)) ref_dp $D/ref_dp.v
python3 -I ${SPEC:-spec_gen.py} $W $P $D/spec_top.v
start=$(date +%s)
gtimeout $T $Y -q -l $D/yosys.log -p "
  read_verilog -I$HF -I$HF/RISCV $HF/HardFloat_primitives.v $RAW
  read_verilog $D/ref_dp.v $D/spec_top.v
  hierarchy -top top
  proc; flatten; opt -fast
  sat -verify -prove bad 0 -show-inputs
" > /dev/null 2>&1
rc=$?
secs=$(( $(date +%s) - start ))
if [ $rc = 0 ] && grep -q 'SUCCESS!' $D/yosys.log; then r=EQUIVALENT
elif [ $rc = 124 ]; then r=TIMEOUT
elif grep -q 'FAIL!' $D/yosys.log; then r=DIFFERENT
else r="ERROR rc=$rc"; fi
echo "w=$W p=$P ${TAG:-hardfloat} $r ${secs}s"
