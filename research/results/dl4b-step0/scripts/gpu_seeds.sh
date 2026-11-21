#!/bin/bash
# DL4b step 0 on glacier (WSL): one arm, seeds in turn; each seed resumes from its
# checkpoint. Exit 3 = yielded (rerun resumes). Usage: gpu_seeds.sh ARM STEPS_TOTAL BATCH SEEDS... 
# env: HOURS (per seed), PSFG (NP)
set -u
ARM=$1; STEPS=$2; BATCH=$3; shift 3
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
D=/mnt/d/rang/dl4b-step0
PY=$HOME/Build/tmp/20261120-dl4b-torch/bin/python
export GPU_CHECK="cmd.exe /c python C:/Users/gijsm/.gpu/gpu_run.py check --owner rang --minutes 15"
EXTRA=""; [ -n "${PSFG:-}" ] && EXTRA="--psfg $PSFG"
for K in "$@"; do
  OUT=$D/runs/$ARM-seed$K
  [ -f "$OUT/done.json" ] && continue
  mkdir -p "$OUT"
  /usr/bin/time -f "wall %e s rss %M KB" -a -o "$OUT/time.txt" "$PY" "$H/examples/dl4b_train.py" train "$D/packs" "$OUT" \
    --arm "$ARM" --seed "$K" --hours "${HOURS}" --steps-total "$STEPS" --batch "$BATCH" $EXTRA \
    ${YIELD:---yield-window 20:50-23:59 --yield-window 06:00-06:50} >> "$OUT/stdout.log" 2>&1
  rc=$?
  echo "$(date +%FT%T) $ARM seed $K rc=$rc" >> "$D/runs/status.log"
  [ $rc -ne 0 ] && exit $rc
done
exit 0
