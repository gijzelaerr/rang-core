#!/bin/bash
# A2's cases under the main checkout's heavy lock, one 1-slot ticket each
# (CASA at OMP 1), two at a time (space rule: about 50 GB per case on D:\wsl),
# D: free space checked (>= 150 GB) before each pair.
P=/mnt/d/rang/outputs/e2b-arms-20261114
cd ~/e2b-arms-20261114
run() {
  n=$1; s=$(date +%s)
  python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 1 --mem 6 -- bash -c "s2=\$(date +%s); bash /mnt/c/Users/gijsm/Worktrees/rang/e2b-arms/research/results/e2b-misses/a2_run.sh case $n 1 > $n.log 2>&1; echo rc=\$? ran_secs=\$((\$(date +%s)-s2)) start=\$s2 >> $n.log"
  echo total_secs=$(( $(date +%s)-s )) >> $n.log
}
for pair in "after-spec match-ones" "match-spec after-ones"; do
  free=$(df -BG --output=avail /mnt/d | tail -1 | tr -dc 0-9)
  echo "D: free ${free} GB before: $pair"
  [ "$free" -lt 250 ] && { echo "stop: under 250 GB free (150 + 2 cases)"; exit 4; }
  for n in $pair; do run $n & sleep 2; done
  wait
done
