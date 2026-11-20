#!/bin/bash
# DL2: write the stage manifests once no teacher stream has run for two checks 120 s apart
# (a re-queue leaves a 3 s gap with no stream; dl2-data.md amendment 8).
R=~/rang-data/outputs/dl2-data-20261119
S=~/Worktrees/rang/dl2-data/research/results/dl2-scripts
cd $R
empty=0
while [ $empty -lt 2 ]; do
  if ps -eo cmd | grep -q "^/bin/bash .*teach_block.sh"; then empty=0; else empty=$((empty+1)); fi
  sleep 120
done
echo "STAGE $(date -u +%FT%TZ) all teacher streams ended; dl2_stage.py" >> logs/teach.log
nice -n 19 ~/Worktrees/rang/dl2-data/.venv-dl2/bin/python $S/dl2_stage.py $R >> logs/teach.log 2>&1
echo "STAGE-END $(date -u +%FT%TZ) rc $?" >> logs/teach.log
