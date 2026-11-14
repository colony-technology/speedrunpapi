#!/bin/zsh
# cross.sh: Icarus against Verilator on every valid finite nonzero input, formats (3,5) (4,7) (5,5).
# Needs the Verilator builds of one.sh. Writes logs/cross.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
HF=${HARDFLOAT:?set HARDFLOAT to the unpacked HardFloat-1 directory}/source
OSS=${EDA_BIN:-$(dirname "$(command -v verilator)")}
cd $HERE || exit 2
mkdir -p cross
: > logs/cross.txt
$OSS/iverilog -V 2>&1 | head -1 >> logs/cross.txt
for WP in "3 5" "4 7" "5 5"; do
  W=${WP% *}; P=${WP#* }
  D=cross/w${W}_p${P}; mkdir -p $D
  $OSS/iverilog -g2005 -o $D/tbi.vvp -P tbi.W=$W -P tbi.P=$P -I $HF -I $HF/RISCV \
      $HF/HardFloat_primitives.v $HF/HardFloat_rawFN.v $HERE/tb_icarus.v || { echo "iverilog failed $W $P" >> logs/cross.txt; continue; }
  (cd $D && $OSS/vvp -n tbi.vvp > /dev/null)
  obj/w${W}_p${P}/sim tables/w${W}_p${P}.bin $D/verilator.dump > /dev/null
  n=$(wc -l < $D/icarus.dump | tr -d ' ')
  if cmp -s $D/icarus.dump $D/verilator.dump; then r=identical; else r=DIFFERENT; fi
  echo "w=$W p=$P lines $n icarus vs verilator: $r" >> logs/cross.txt
done
