#!/bin/zsh
# run_states.sh: the Verilog anchor of hf_datapath.bv, then phase-state counts. Writes logs/states.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
cd $HERE || exit 2
mkdir -p logs
[ "$1" = "noanchor" ] || ./anchor/anchor.sh
: > logs/states.txt
{ python3 -I check_mark.py; python3 -I check_design1c.py design1c.bv; } >> logs/states.txt 2>&1
for desc in round_mark.bv design1c.bv; do
  for r in ne na tz aw odd; do
    a=()
    for k in ne na tz aw odd; do if [ $r = $k ]; then a+=($k=1); else a+=($k=0); fi; done
    python3 -I bvfsm.py states $desc mark one $a >> logs/states.txt 2>&1
  done
done
echo "done $(date '+%H:%M:%S')" >> logs/states.txt
