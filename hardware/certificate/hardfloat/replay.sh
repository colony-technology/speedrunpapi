#!/bin/zsh
# replay.sh HardFloat-1.zip : replays every check of the HardFloat certificate from this folder.
# Needs: zsh, Python 3 (3.15.2 used), z3 on PATH or $Z3 (Z3 5.3.3 used), and in one directory $EDA_BIN
# (default: where `verilator` is) Verilator (5.055 used), Icarus Verilog iverilog/vvp (14.0 devel used) and
# Yosys (0.70+385 used), as the oss-cad-suite ships them. Optional: HEAVY=command prefix for heavy steps.
# About 30 minutes on an Apple M1 mini. Prints each check; exit status 0 only if every check gives its
# recorded result.
set -u
ZIP=${1:?usage: replay.sh path/to/HardFloat-1.zip}
C=$(cd "$(dirname "$0")" && pwd)
HEAVY=${HEAVY:-}
fail=0
step() { echo; echo "== $(date '+%H:%M:%S') $*"; }
want() { if eval "$1"; then echo "   ok: $2"; else echo "   FAILED: $2"; fail=1; fi; }

step "unit identity"
want '[ "$(shasum -a 256 "$ZIP" | cut -d" " -f1)" = 6b3757c9fbfa2230c6a2b84605e39372cb589dd7500e979c4f0b8ecc8a03b14b ]' "HardFloat-1.zip SHA-256"
mkdir -p $C/work
[ -d $C/work/HardFloat-1 ] || (cd $C/work && unzip -q "$ZIP")
export HARDFLOAT=$C/work/HardFloat-1
want '[ -f $HARDFLOAT/source/HardFloat_rawFN.v ]' "archive unpacked to work/HardFloat-1"

step "stage 1: reference against the host's binary16 and binary32"
python3 -I $C/stage1/refcheck.py 20000; want '[ $? = 0 ]' "0 differences"

step "stage 1: exhaustive audit, 19 formats"
${=HEAVY} $C/stage1/run_all.sh
python3 -I $C/stage1/table.py $C/stage1/logs/summary.txt | tail -5
want 'python3 -I $C/stage1/table.py $C/stage1/logs/summary.txt | grep -q "documented formats: inputs 3,297,497,088, finite nonzero 77,893,632, special 3,219,603,456, mismatches 0"' "documented formats: 0 mismatches"

step "stage 1: planted fault (ties-to-even clear removed), w=4 p=5"
mkdir -p $C/work/mutant
sed 's/& ~(roundingMode_near_even \&\& roundPosBit/\& ~(1'"'"'b0 \&\& roundPosBit/' $HARDFLOAT/source/HardFloat_rawFN.v > $C/work/mutant/HardFloat_rawFN.v
(cd $C/stage1 && RAW=$C/work/mutant/HardFloat_rawFN.v TAG=mutant_ ./one.sh 4 5)
want 'grep -q "mismatches 960 " $C/stage1/logs/mutant_w4_p5.log' "960 mismatches found"

step "stage 1: Icarus against Verilator"
${=HEAVY} $C/stage1/cross.sh; cat $C/stage1/logs/cross.txt
want '[ $(grep -c identical $C/stage1/logs/cross.txt) = 3 ]' "3 formats identical"

step "stage 2: descriptions against the definition, emitter against the semantics"
python3 -I $C/stage2/check_ref.py $C/stage2/ref_round.bv; want '[ $? = 0 ]' "ref_round.bv"
python3 -I $C/stage2/check_ref.py $C/stage2/hf_datapath.bv; want '[ $? = 0 ]' "hf_datapath.bv"
python3 -I $C/stage2/check_lemma.py; want '[ $? = 0 ]' "lemma L1 sides, N = 2..11"
python3 -I $C/stage2/check_mark.py; want '[ $? = 0 ]' "round_mark.bv"
python3 -I $C/stage2/check_design1c.py $C/stage2/design1c.bv; want '[ $? = 0 ]' "design1c.bv"
python3 -I $C/stage2/bvfsm.py selftest $C/stage2/hf_datapath.bv 12 60; want '[ $? = 0 ]' "automaton = direct evaluation (hf)"
python3 -I $C/stage2/bvfsm.py selftest $C/stage2/ref_round.bv 12 60; want '[ $? = 0 ]' "automaton = direct evaluation (ref)"
for N in 6 7; do python3 -I $C/stage2/emitcheck.py $C/stage2/hf_datapath.bv $N; want '[ $? = 0 ]' "emitter, N=$N, every input"; done
for N in 28 117; do python3 -I $C/stage2/emitcheck.py $C/stage2/hf_datapath.bv $N 5000; want '[ $? = 0 ]' "emitter, N=$N, random"; done

step "stage 2: equivalence for every width, broken copies, lemma L1"
${=HEAVY} $C/stage2/run_equiv.sh
for f in hf_ref lemma_cu lemma_cu_broken broken_ref broken2_ref; do echo "-- $f"; grep -v '^  live\|^  product:' $C/stage2/logs/$f.txt | tail -12; done
want 'grep -q "^EQUAL on every word length" $C/stage2/logs/hf_ref.txt' "HardFloat datapath = definition, every width"
want 'grep -q "^EQUAL on every word length" $C/stage2/logs/lemma_cu.txt' "lemma L1, every width"
want 'grep -q "^COUNTEREXAMPLE" $C/stage2/logs/lemma_cu_broken.txt' "broken lemma: counterexample"
want 'grep -q "^COUNTEREXAMPLE" $C/stage2/logs/broken_ref.txt' "broken copy 1: counterexample"
want 'grep -q "^COUNTEREXAMPLE" $C/stage2/logs/broken2_ref.txt' "broken copy 2: counterexample"

step "stage 2: the transcription against HardFloat's own netlist, p = 3..113 (Yosys SAT)"
${=HEAVY} $C/stage2/formal/all.sh; tail -12 $C/stage2/formal/formal.txt
want '[ $(grep -c " hf_datapath.bv EQUIVALENT" $C/stage2/formal/formal.txt) = 111 ]' "111 widths equivalent"
want '[ $(grep -c "broken.*DIFFERENT" $C/stage2/formal/formal.txt) = 10 ]' "broken copies: 10 of 10 different"

step "stage 2: simulation anchor of the description, and phase-state counts"
${=HEAVY} $C/stage2/run_states.sh
cat $C/stage2/anchor/anchor.txt; grep '^states\|vs ' $C/stage2/logs/states.txt
want '[ $(grep -c "differences 0" $C/stage2/anchor/anchor.txt) = 7 ]' "anchor: 7 widths, 0 differences"
want 'grep -q "design1c.bv mark=one fixed aw=0 na=0 ne=1 odd=0 tz=0: deterministic states 41, minimal classes 14: before the phase change 7, after 7" $C/stage2/logs/states.txt' "design I, nearest even: 7 + 7"

step "stage 3: exponent stage for every format (z3)"
python3 -I $C/stage3/expstage.py $C/stage3/smt | tee $C/stage3/expstage.replay.txt
want '[ $(grep -c "^hardfloat .*proved$" $C/stage3/expstage.replay.txt) = 9 ]' "9 claims proved"
want '[ $(grep -c "^mut_.*COUNTERMODEL$" $C/stage3/expstage.replay.txt) = 9 ]' "planted faults give 9 counter-models"

step "stage 3: the model against HardFloat's outputs"
for wp in "3 5" "4 7" "5 5"; do python3 -I $C/stage3/factcheck.py ${=wp} $C/stage1/cross/w${wp% *}_p${wp#* }/verilator.dump; want '[ $? = 0 ]' "factcheck $wp"; done

echo; echo "== $(date '+%H:%M:%S') replay $([ $fail = 0 ] && echo PASSED || echo FAILED)"
exit $fail
