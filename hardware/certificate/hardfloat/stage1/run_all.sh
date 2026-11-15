#!/bin/zsh
# run_all.sh: stage 1 over every format w = 3..5, p = 3..7, and w = 5, p = 8..11. Writes logs/summary.txt.
HERE=$(cd "$(dirname "$0")" && pwd)
cd $HERE || exit 2
: > logs/summary.txt
for W in 3 4 5; do
  PS=(3 4 5 6 7); [ $W = 5 ] && PS=(3 4 5 6 7 8 9 10 11)
  for P in $PS; do
    ./one.sh $W $P > /dev/null
    grep '^w=' logs/w${W}_p${P}.log | grep -v records >> logs/summary.txt
  done
done
echo "done $(date '+%H:%M:%S')" >> logs/summary.txt
