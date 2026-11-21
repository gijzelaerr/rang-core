#!/bin/bash
# P validation for seed K once its run has finished: export best.pt, two 4-slot lanes (one per tau), score.
K=$1
D=/d/rang/dl4b-step1
until [ -f $D/runs/seed$K/done.json ]; do sleep 120; done
MSYS2_ARG_CONV_EXCL="*" wsl -d Ubuntu -- bash -c "\$HOME/Build/tmp/20261120-dl4b-torch/bin/python /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/examples/dl4b_train1.py export /mnt/d/rang/dl4b-step1/runs/seed$K/best.pt /mnt/d/rang/dl4b-step1/onnx/seed$K.onnx" > $D/pval-$K-export.log 2>&1
cd /c/Users/gijsm/Github/rang
for t in 3 5; do
  MSYS2_ARG_CONV_EXCL="*" python tools/heavy_lock.py run --slots 4 --mem 16 -- wsl -d Ubuntu -- bash /mnt/d/rang/dl4b-step1/pval-lane.sh $K V1,V2,V3,V4 $t > $D/pval-$K-t$t.log 2>&1 &
done
wait
ARMS=W1,W5$(for t in 3 5; do for k in 1 2 3; do printf ",P-s$K-t$t-K$k"; done; done)
MSYS2_ARG_CONV_EXCL="*" python tools/heavy_lock.py run --slots 2 --mem 16 -- wsl -d Ubuntu -- bash -c "cd /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e && ~/Github/rang/.venv/bin/python examples/dl4b_step1.py score /home/gijsm/Build/tmp/20261121-dl4b-step1/skies /mnt/d/rang/dl4b-step1/score-val-P-s$K.json --names V1,V2,V3,V4 --arms $ARMS" > $D/pval-$K-score.log 2>&1
tail -40 $D/pval-$K-score.log | grep -v heavy_lock | cut -c1-230
