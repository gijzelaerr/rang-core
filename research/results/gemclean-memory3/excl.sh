#!/bin/bash
# research/gemclean-memory3.md section 4: exclusive pairs, this branch's binary f20c06a
cd ~/Worktrees/rang/gemclean-memory3
B=D:/rang/outputs/gemclean-memory3-20261117/bin/gemclean-ab-f20c06a.exe
F=research/results/gemclean-memory3/field.sh
for fid in 2 0 1; do
  for arm in plain reorder; do
    x=(); [ $arm = reorder ] && x=(-reorder)
    python ~/Github/rang/tools/heavy_lock.py run -- "C:/Program Files/Git/bin/bash.exe" $F $fid x-$arm $B -memory-report "${x[@]}"
  done
done
echo done > D:/rang/outputs/gemclean-memory3-20261117/excl.done
