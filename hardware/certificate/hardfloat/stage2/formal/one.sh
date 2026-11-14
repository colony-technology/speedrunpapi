#!/bin/zsh
# one.sh P [TIMEOUT]: formal equivalence, at precision P and the smallest exponent width HardFloat documents
# for it (p <= 2^(w-2) + 3, w >= 3), of HardFloat's own datapath signals and the module emitted from
# hf_datapath.bv at N = P + 4. HardFloat's roundMask is cut into a free input (yosys expose -input);
# roundedSig, roundPosBit, anyRoundExtra, anyRound are brought out. The miter asserts that, whenever the
# description's assumptions hold (mask = ones below R, R >= 2; a valid mode), the four signals are equal.
# Prints one line: P W result seconds.
set -u
P=$1; T=${2:-600}
W=3; while [ $(( (1 << (W - 2)) + 3 )) -lt $P ]; do W=$((W + 1)); done
HERE=$(cd "$(dirname "$0")" && pwd)
HF=${HARDFLOAT:?set HARDFLOAT to the unpacked HardFloat-1 directory}/source
Y=${EDA_BIN:-$(dirname "$(command -v yosys)")}/yosys
cd $HERE || exit 2

DESC=${DESC:-../hf_datapath.bv}; D=${TAG:-}p$P; mkdir -p $D
python3 -I ../bv2v.py $DESC $((P + 4)) hf_bv $D/hf_bv.v
cat > $D/top.v <<EOT
module top(input [$((P+2)):0] sig, input [$((P+2)):0] mask, input m2, input m1, input m0, input sign,
           input control, input [$((W+1)):0] sexp, output bad);
  wire [$((P+1)):0] g_rs, b_rs; wire g_rpb, g_ext, g_any, b_rpb, b_ext, b_any, valid;
  wire [$((W+P)):0] o; wire [4:0] f;
  hf_cut g(.control(control), .invalidExc(1'b0), .infiniteExc(1'b0), .in_isNaN(1'b0), .in_isInf(1'b0),
           .in_isZero(1'b0), .in_sign(sign), .in_sExp(sexp), .in_sig(sig), .roundingMode({m2, m1, m0}),
           .out(o), .exceptionFlags(f), .gmask(mask), .grs(g_rs), .grpb(g_rpb), .gext(g_ext), .gany(g_any));
  hf_bv b(.sig(sig), .mask(mask), .m2(m2), .m1(m1), .m0(m0), .sign(sign), .roundedSig(b_rs),
          .roundPosBit(b_rpb), .anyRoundExtra(b_ext), .anyRound(b_any), .valid(valid));
  assign bad = valid && ((g_rs != b_rs) || (g_rpb != b_rpb) || (g_ext != b_ext) || (g_any != b_any));
endmodule
EOT
G=roundAnyRawFNToRecFN.genblk2
start=$(date +%s)
gtimeout $T $Y -q -l $D/yosys.log -p "
  read_verilog -I$HF -I$HF/RISCV $HF/HardFloat_primitives.v $HF/HardFloat_rawFN.v
  chparam -set expWidth $W -set sigWidth $P roundRawFNToRecFN
  hierarchy -top roundRawFNToRecFN
  proc; flatten; opt_clean
  cd roundRawFNToRecFN
  rename $G.roundMask gmask
  rename $G.roundedSig grs
  rename $G.roundPosBit grpb
  rename $G.anyRoundExtra gext
  rename $G.anyRound gany
  expose -input w:gmask
  expose w:grs w:grpb w:gext w:gany
  cd ..
  rename roundRawFNToRecFN hf_cut
  read_verilog $D/hf_bv.v $D/top.v
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
echo "p=$P w=$W $(basename $DESC) $r ${secs}s"
