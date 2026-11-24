#!/bin/bash
# F7 D9b held-out read (research/f7-flagger.md, D9b freeze): the frozen target candidate
# (method.json: level 70, seed 2, tau -4.5, W4 off; weights sha256 d196a343...) scored ONCE on the
# held-out target sets: SARAO 1678312253 scans 36/40/44, 1674958551 31/35/39, 1579022459
# 115/117/121; ESO137 chunks 1, 3, 5, 7, 9, 15, 17; f4sim-t. T and A are computed here (no cache).
# A rerun skips finished sets (done-markers); no set is read twice.
O=$HOME/rang-data/outputs/f7-d9b-20261123
PY=$HOME/Worktrees/rang/f7-draft/.venv/bin/python
source $(dirname $0)/common.sh
M=$O/method-frozen.json
[ -f $M ] || { log "no frozen method"; exit 1; }
HA="--method $M --heldout-read --sarao-root $C --data-root $D --ao-sif $SIF"
SETS="sarao:1678312253:36 sarao:1678312253:40 sarao:1678312253:44 sarao:1674958551:31 sarao:1674958551:35 sarao:1674958551:39 sarao:1579022459:115 sarao:1579022459:117 sarao:1579022459:121 eso:1 eso:3 eso:5 eso:7 eso:9 eso:15 eso:17"
for s in $SETS; do job held-${s//:/-} 8 32 $PY examples/f6_heldout.py real $O/held-target --set $s $HA & sleep 20; done
job held-sim 4 16 $PY examples/f6_heldout.py sim $O/held-target --class target $HA &
wait
$PY examples/f6_verdict.py $O/held-verdict-target.json --class target --run $O/held-target --sets $(echo $SETS | tr " " ,) > $O/held-verdict.log 2>&1; log "d9b HELD-OUT verdict: $(tail -n 1 $O/held-verdict.log)"; touch $O/held.done
