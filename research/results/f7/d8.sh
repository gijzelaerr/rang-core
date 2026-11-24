#!/bin/bash
# F7 D8 (research/f7-flagger.md), validation only, no training: the plane probe with D7's
# weights at level 40, k = 1, G-drop's three draws on ESO137 chunk 10, one SARAO draw.
O=$HOME/rang-data/outputs/f7-d8-20261123
source $(dirname $0)/common.sh
WT=$D7/train-target/seed-2/weights.npz
for s in 20265301 20265302 20265303; do
  job eso-10-k1-$s 6 24 $PY examples/f5_f6_probe.py $O/eso-10-k1-$s.json --weights $WT --tau -4.0 --set eso:10 --level 40 --k 1 --seed $s --nsel 256 --data-root $D --sarao-root $C &
done
job sarao-111-k1 6 24 $PY examples/f5_f6_probe.py $O/sarao-111-k1.json --weights $WT --tau -4.0 --set sarao:1573212012:111 --level 40 --k 1 --nsel 256 --data-root $D --sarao-root $C &
wait; touch $O/d8.done; log "D8 done"
