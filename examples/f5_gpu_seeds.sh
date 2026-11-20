#!/bin/bash
# F5 Stage 4 on glacier: seeds 1-3 of one class in ONE process (the shards are
# loaded once, about 25 GB; three processes would not fit WSL's memory). Each
# seed keeps its own model, optimiser, batch generator and checkpoint
# (OUT/seed-K), so each run is bit-identical to the same seed alone
# (tests/test_f5_flag.py). Exit 3 = yielded the GPU; rerun resumes.
#
# Usage: bash examples/f5_gpu_seeds.sh SHARDS OUT
set -u
SHARDS=$1; OUT=$2
PY=${F5_PY:-$HOME/Build/tmp/20261119-f5-torch/bin/python}
HERE=$(cd "$(dirname "$0")/.." && pwd)
export GPU_CHECK=${GPU_CHECK:-"cmd.exe /c python C:/Users/gijsm/.gpu/gpu_run.py check --owner rang --minutes 15"}
mkdir -p "$OUT"
[ -f "$OUT/seed-1/weights.npz" ] && [ -f "$OUT/seed-2/weights.npz" ] && [ -f "$OUT/seed-3/weights.npz" ] && exit 0
/usr/bin/time -f "wall %e s rss %M KB" -a -o "$OUT/seeds.time" "$PY" "$HERE/examples/f5_train.py" "$SHARDS" "$OUT" \
  --seed 1,2,3 --steps 30000 >> "$OUT/seeds.log" 2>&1
rc=$?
echo "$(date +%FT%T) seeds rc=$rc" >> "$OUT/status.log"
exit $rc
