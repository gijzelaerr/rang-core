#!/bin/bash
# DL4b step 1 on glacier (WSL): seeds in turn, each resuming from its checkpoint.
# Exit 3 = yielded (rerun resumes). Usage: gpu_seeds.sh STEPS_TOTAL BATCH SEEDS...  env: HOURS
set -u
STEPS=$1; BATCH=$2; shift 2
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
S=$HOME/Build/tmp/20261121-dl4b-step1
D=/mnt/d/rang/dl4b-step1
PY=$HOME/Build/tmp/20261120-dl4b-torch/bin/python
export GPU_CHECK="cmd.exe /c python C:/Users/gijsm/.gpu/gpu_run.py check --owner rang --minutes 15"
for K in "$@"; do
  OUT=$D/runs/seed$K
  [ -f "$OUT/done.json" ] && continue
  mkdir -p "$OUT"
  /usr/bin/time -f "wall %e s rss %M KB" -a -o "$OUT/time.txt" "$PY" "$H/examples/dl4b_train1.py" train "$S/skies" "$OUT" \
    --seed "$K" --hours "$HOURS" --steps-total "$STEPS" --batch "$BATCH" \
    --yield-window 06:00-06:50 \
    >> "$OUT/stdout.log" 2>&1
  rc=$?
  echo "$(date +%FT%T) seed $K rc=$rc" >> "$D/runs/status.log"
  [ $rc -ne 0 ] && exit $rc
done
exit 0
