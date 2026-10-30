#!/bin/bash
# Interleaved A/B benchmark of rows-as-lanes on tricolour 0.5.0-dev, one pinned core, one thread.
set -u
S=$(cd "$(dirname "$0")" && pwd)
B=~/Build/tmp/20261030-upstream-prs
cd $B/tricolour
[ -d ../tricolour-base ] || git worktree add -q --detach ../tricolour-base origin/0.5.0-dev
if [ ! -d ../tricolour-lanes ]; then
  git worktree add -q -b lanes-frequency-axis ../tricolour-lanes origin/0.5.0-dev
  (cd ../tricolour-lanes && python3 "$S/lanes.py")
fi
mkdir -p $B/bench-lanes
CORE=${CORE:-13}
ROUNDS=${ROUNDS:-7}
export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for v in base lanes; do mkdir -p $B/bench-lanes/cache-$v; done
for r in $(seq 1 $ROUNDS); do
  for v in base lanes; do
    NUMBA_CACHE_DIR=$B/bench-lanes/cache-$v PYTHONPATH=$B/tricolour-$v/src \
      /usr/bin/time -f "$v round $r wall %e s maxrss %M KB" \
      taskset -c $CORE $B/venv-tricolour-dev/bin/python "$S/bench_lanes.py" $v 5 $B/bench-lanes/flags-$v.npz \
      >> $B/bench-lanes/results.jsonl
  done
done
uptime
