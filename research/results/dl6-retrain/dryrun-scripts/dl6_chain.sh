#!/bin/bash
# DL6 dry run on nash (research/dl6-retrain.md section 8), one heavy-lock
# booking for the chain (8 slots), nice 19 + ionice -c3 from the caller.
# Each step writes <step>.log, <step>.time and <step>.done; a rerun skips
# done steps and stops at the first failure.
set -u
R=$HOME/rang-data/outputs/dl6-dryrun-20261120
W=$HOME/Worktrees/rang/dl6-dryrun
PY=$W/.venv/bin/python
SIF=$HOME/rang-data/outputs/dl3-f5-20261119/images/rang-aflag-aoflagger_3.5.0.sif
MS=$HOME/rang-data/outputs/dl2-data-20261119/ms/1735892129
export DL6_SCANS=$R/scans DL6_LABELS=$HOME/rang-data/outputs/dl2-data-20261119/labels
export RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8
cd "$W"
step() {
  local name=$1; shift
  [ -f "$R/$name.done" ] && return 0
  echo "$(date -u +%FT%TZ) start $name" >> "$R/chain.log"
  /usr/bin/time -f "wall %e s rss %M KB" -o "$R/$name.time" "$@" > "$R/$name.log" 2>&1
  local rc=$?
  echo "$(date -u +%FT%TZ) $name rc=$rc" >> "$R/chain.log"
  [ $rc -ne 0 ] && exit $rc
  touch "$R/$name.done"
}
D=$R/dl6_run.py
step check-loader $PY $R/dl6_check_loader.py $R/scans/scan019.npz $MS/scan019.ms
step cache $PY $D cache $R/flags
step shards-validation $PY $D examples/f5_shards.py $R/shards --class calibrator --role validation --level 0 --degree 1 --flags-from $R/flags --only-real --ao-sif $SIF
step shards-train $PY $D examples/f5_shards.py $R/shards --class calibrator --role train --level 0 --degree 1 --flags-from $R/flags --only-real --ao-sif $SIF
# Training runs on glacier's GPU (gpu_run.py, owner rang; coordinator 2026-11-20):
# the chain stops here until train/seed-1/weights.npz is copied back.
if [ ! -f "$R/train/seed-1/weights.npz" ]; then
  echo "$(date -u +%FT%TZ) awaiting glacier training" >> "$R/chain.log"
  exit 0
fi
step tau $PY $D examples/f5_tau.py $R/tau --class calibrator --weights $R/train/seed-1/weights.npz --level 0 --degree 1 --flags-from $R/flags
step validation $PY $D examples/f5_heldout.py real $R/val --set dl2:1735892129:scan019 --method $R/tau/method.json --validation --ao-sif $SIF
echo "$(date -u +%FT%TZ) chain done" >> "$R/chain.log"
