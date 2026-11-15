#!/bin/zsh
# run_equiv.sh: the stage 2 equivalence checks. Each result goes to logs/<name>.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
cd $HERE || exit 2
mkdir -p logs
for pair in "hf_ref:hf_datapath.bv:ref_round.bv" "broken_ref:hf_datapath_broken.bv:ref_round.bv" "lemma_cu:lemma_cu_c_lhs.bv:lemma_cu_c_rhs.bv" "lemma_cu_broken:lemma_cu_c_lhs.bv:lemma_cu_c_rhs_broken.bv" \
            "broken2_ref:hf_datapath_broken2.bv:ref_round.bv"; do
  name=${pair%%:*}; rest=${pair#*:}; a=${rest%%:*}; b=${rest#*:}
  { echo "== $(date '+%H:%M:%S') bvfsm.py equiv $a $b"; python3 -I bvfsm.py equiv $a $b; echo "exit $?";
    echo "== $(date '+%H:%M:%S') end"; } > logs/$name.txt 2>&1
done
