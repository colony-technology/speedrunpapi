#!/bin/zsh
# run_lemma.sh: lemma L1 for every width (causal form). Writes logs/lemma_cu.txt.
cd "$(dirname "$0")" || exit 2
{ echo "== $(date +%H:%M:%S) bvfsm.py equiv lemma_cu_c_lhs.bv lemma_cu_c_rhs.bv"; python3 -I bvfsm.py equiv lemma_cu_c_lhs.bv lemma_cu_c_rhs.bv; echo "exit $?"; echo "== $(date +%H:%M:%S) end"; } > logs/lemma_cu.txt 2>&1
