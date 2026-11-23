#!/bin/bash
# Detached (WSL): Sunday 06:50 onwards, P validation lanes one at a time through glacier's lock,
# then scoring of seeds 2 and 3. Logs to /mnt/d/rang/dl4b-step1/sunday-pval.log.
L=/mnt/d/rang/dl4b-step1/sunday-pval.log
LOCK="python C:/Users/gijsm/Github/rang/tools/heavy_lock.py run"
echo "$(date +%FT%T) armed (pid $$)" >> $L
: # no time gate (glacier free after #47, coordinator 02:1x)
lane() { echo "$(date +%FT%T) lane seed $1 tau $2" >> $L
  cmd.exe /c "cd /d C:\Users\gijsm\Github\rang && set MSYS2_ARG_CONV_EXCL=* && $LOCK --slots 4 --mem 16 -- wsl -d Ubuntu -- bash /mnt/d/rang/dl4b-step1/pval-lane.sh $1 V1,V2,V3,V4 $2" >> /mnt/d/rang/dl4b-step1/pval-$1-t$2.log 2>&1
  echo "$(date +%FT%T) lane seed $1 tau $2 exit $?" >> $L; }
lane 2 5
until [ -f /mnt/d/rang/dl4b-step1/runs/seed3/done.json ]; do sleep 120; done
$HOME/Build/tmp/20261120-dl4b-torch/bin/python /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/examples/dl4b_train1.py export /mnt/d/rang/dl4b-step1/runs/seed3/best.pt /mnt/d/rang/dl4b-step1/onnx/seed3.onnx >> $L 2>&1
lane 3 3
lane 3 5
for K in 2 3; do
  ARMS=W1,W5$(for t in 3 5; do for k in 1 2 3; do printf ",P-s$K-t$t-K$k"; done; done)
  cd /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e && ~/Github/rang/.venv/bin/python examples/dl4b_step1.py score /home/gijsm/Build/tmp/20261121-dl4b-step1/skies /mnt/d/rang/dl4b-step1/score-val-P-s$K.json --names V1,V2,V3,V4 --arms $ARMS >> $L 2>&1
done
echo "$(date +%FT%T) all done" >> $L
