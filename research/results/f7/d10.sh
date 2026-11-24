#!/bin/bash
# F7 D10 (research/f7-flagger.md), validation only, calibrators: P3 on top of D1. F6's calibrator
# shards (level 20) linked, plus 4 realisations of each reserved LUNO group (MAIN_8-11, 13, 15);
# balanced real batches, seed 2, tau by f6_tau, W4 off; complete calibrator validation scorer.
# dl3-f6's venv (common.sh): rang's python/ and core/ at level 20 identical to f7-draft's.
# Bookings: F6's calibrator shards 33 GB (book 48), trainer 153 GB (book 160).
O=$HOME/rang-data/outputs/f7-d10-20261123
source $(dirname $0)/common.sh
FLC=$D/outputs/f4-20261111-06-shards-cal
for r in train validation; do mkdir -p $O/shards/calibrator/$r/records
  for f in $F6/shards/calibrator/$r/*.npz $F6/shards/calibrator/$r/*.sha256; do ln -sf $f $O/shards/calibrator/$r/; done
  for f in $F6/shards/calibrator/$r/records/*.json; do ln -sf $f $O/shards/calibrator/$r/records/; done; done
job shards-reserved 12 48 $PY examples/f6_shards.py $O/shards --class calibrator --role train --level 20 --degree 1 --flags-from $FLC --data-root $D --sarao-root $C --ao-sif $SIF --sources none --reserved-luno $D/outputs/f5-20261120-reserved-fetch/objects || exit 1
log "train shards: $(ls $O/shards/calibrator/train/*.npz | wc -l) ($(ls $O/shards/calibrator/train/luno-*.npz | wc -l) LUNO)"
job train 12 160 $PY examples/f5_train.py $O/shards/calibrator $O/train-calibrator/seed-2 --seed 2 --steps 30000 --device cpu --balance-real || exit 1
job tau 8 40 $PY examples/f6_tau.py $O/tau-calibrator --class calibrator --train-dir $O/train-calibrator --shards $O/shards --level 20 --degree 1 --flags-from $FLC --data-root $D --sarao-root $C || exit 1
$PY -c "
import json;m=json.load(open('$O/tau-calibrator/method.json'));m['kappa']=None;m['method']='N5';m['note']='F7 D10: P1 + P3, W4 off'
json.dump(m,open('$O/method.json','w'),indent=1)"
export F6_A_FROM=$F6/val-calibrator
HA="--method $O/method.json --validation --sarao-root $C --data-root $D --ao-sif $SIF"
SETS="luno:MAIN_7 sarao:1573212012:1 sarao:1573212012:3 sarao:1573212012:5"
for s in $SETS; do job val-${s//:/-} 8 32 $PY examples/f6_heldout.py real $O/val-calibrator --set $s $HA & done
job val-sim 4 16 $PY examples/f6_heldout.py sim $O/val-calibrator --class calibrator $HA &
wait
$PY examples/f6_verdict.py $O/val-verdict-calibrator.json --class calibrator --run $O/val-calibrator --sets $(echo $SETS | tr " " ,) > $O/val-verdict.log 2>&1; log "verdict: $(tail -n 1 $O/val-verdict.log)"; touch $O/d10.done
