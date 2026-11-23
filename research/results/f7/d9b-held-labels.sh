#!/bin/bash
# F7 D9b held-out read, amendment H1 (research/f7-flagger.md): DL2 never labelled the held-out
# SARAO blocks, so T (DL2's rang teacher) and A (DL2's AOFlagger 2.13 teacher) are built here with
# DL2's own runner and pins (dl2_teach.py --heldout-read; rang core sha256 ce8d03ce..., stimela
# AOFlagger 1.2.0 image fd89f5d9...), the nine held-out target scans only, then the held-out chain
# is rerun (it skips the ESO137 and simulation sets already done; each set is still scored once).
O=$HOME/rang-data/outputs/f7-d9b-20261123
source $(dirname $0)/common.sh
R2=$HOME/rang-data/outputs/dl2-data-20261119
S2=$HOME/Worktrees/rang/dl2-data/research/results/dl2-scripts
PY2=$HOME/Worktrees/rang/dl2-data/.venv-dl2/bin/python
teach(){ job labels-$1 8 48 bash -c "cd $R2 && $PY2 -u $S2/dl2_teach.py $R2 rang,aoflagger $1 --scans ${*:2} --threads 8 --heldout-read"; }
teach 1678312253 36 40 44 & sleep 30
teach 1674958551 31 35 39 & sleep 30
teach 1579022459 115 117 121 &
wait
for b in 1678312253 1674958551 1579022459; do [ -f $O/labels-$b.done ] || { log "labels-$b FAILED, held-out rerun not started"; exit 1; }; done
# the first chain's ESO137 and simulation jobs must have ended before the rerun
while pgrep -f "f6_heldout.py (real|sim) $O/held-target" > /dev/null; do sleep 120; done
bash research/results/f7/d9b-held.sh
