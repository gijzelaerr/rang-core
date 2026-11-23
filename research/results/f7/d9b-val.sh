#!/bin/bash
# F7 D9b (research/f7-flagger.md), validation only: D9b passed the ESO137 screen, so the complete
# target validation scorer as D7's (ESO137 chunk 10, 1573212012 scans 111/113/115, simulations),
# then f6_verdict. A reused from D7's run (same sets, A does not depend on the level).
O=$HOME/rang-data/outputs/f7-d9b-20261123
PY=$HOME/Worktrees/rang/f7-draft/.venv/bin/python
source $(dirname $0)/common.sh
export F6_A_FROM=$HOME/rang-data/outputs/f7-d7-20261122/val-target
HA="--method $O/method.json --validation --sarao-root $C --data-root $D --ao-sif $SIF"
SETS="eso:10 sarao:1573212012:111 sarao:1573212012:113 sarao:1573212012:115"
for s in $SETS; do job d9b-val-${s//:/-} 8 32 $PY examples/f6_heldout.py real $O/val-target --set $s $HA & done
job d9b-val-sim 4 16 $PY examples/f6_heldout.py sim $O/val-target --class target $HA &
wait
$PY examples/f6_verdict.py $O/val-verdict-target.json --class target --run $O/val-target --sets $(echo $SETS | tr " " ,) > $O/val-verdict.log 2>&1; log "d9b verdict: $(tail -n 1 $O/val-verdict.log)"; touch $O/val.done
