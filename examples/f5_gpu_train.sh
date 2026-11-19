#!/bin/bash
# F5 Stage 4 on glacier (research/f5-flagger.md, section 9), run inside WSL by
# examples/f5_gpu_train.py under gpu_run.py: the resume test, then seeds 1-3
# of one class. Resumable: each step skips if its weights exist, and a
# trainer resumes from its checkpoint. Exit 3 = yielded the GPU (rerun later).
#
# Usage: bash examples/f5_gpu_train.sh SHARDS OUT [resume|seeds|all]
set -u
SHARDS=$1
OUT=$2
WHAT=${3:-all}
PY=${F5_PY:-$HOME/Build/tmp/20261119-f5-torch/bin/python}
HERE=$(cd "$(dirname "$0")/.." && pwd)
T=$HERE/examples/f5_train.py
export GPU_CHECK=${GPU_CHECK:-"cmd.exe /c python C:/Users/gijsm/.gpu/gpu_run.py check --owner rang --minutes 15"}
mkdir -p "$OUT"
step() {  # name, args...
  local name=$1; shift
  [ -f "$OUT/$name/weights.npz" ] && return 0
  /usr/bin/time -f "wall %e s rss %M KB" -a -o "$OUT/$name.time" "$PY" "$T" "$SHARDS" "$OUT/$name" "$@" >> "$OUT/$name.log" 2>&1
  local rc=$?
  [ $rc -eq 3 ] && exit 3
  [ $rc -ne 0 ] && { echo "$name failed rc=$rc" >> "$OUT/status.log"; exit $rc; }
  echo "$name done" >> "$OUT/status.log"
}
if [ "$WHAT" = resume ] || [ "$WHAT" = all ]; then
  step resume-a --seed 1 --steps 3000
  if [ ! -f "$OUT/resume-b/weights.npz" ] && [ ! -f "$OUT/resume-b/ckpt.pt" ]; then
    # Interrupted at step 1,500 (a checkpoint, no weights), then resumed.
    "$PY" "$T" "$SHARDS" "$OUT/resume-b" --seed 1 --steps 3000 --stop-at 1500 >> "$OUT/resume-b.log" 2>&1
    rc=$?
    [ $rc -eq 3 ] && exit 3
    [ $rc -ne 0 ] && { echo "resume-b first half failed rc=$rc" >> "$OUT/status.log"; exit $rc; }
  fi
  step resume-b --seed 1 --steps 3000
  step resume-seed2 --seed 2 --steps 3000
  "$PY" - "$OUT" <<'PY'
import json, sys
import numpy as np
o = sys.argv[1]
a, b, c = (np.load(f"{o}/{n}/weights.npz")["flat"] for n in ("resume-a", "resume-b", "resume-seed2"))
la, lb, lc = (json.load(open(f"{o}/{n}/train.json"))["validation_loss"] for n in ("resume-a", "resume-b", "resume-seed2"))
rec = {"identical": bool(np.array_equal(a, b)), "max_abs_diff": float(np.abs(a - b).max()),
       "val_loss": {"uninterrupted": la, "resumed": lb, "seed2": lc},
       "seed_spread_max_abs": float(np.abs(a - c).max())}
json.dump(rec, open(f"{o}/resume-test.json", "w"), indent=1)
print(json.dumps(rec))
PY
fi
if [ "$WHAT" = seeds ] || [ "$WHAT" = all ]; then
  for s in 1 2 3; do step "seed-$s" --seed "$s" --steps 30000; done
fi
