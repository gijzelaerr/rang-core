#!/usr/bin/env bash
# sim.sh OUT SKY [--sky-seed X --noise-seed Y] : one simulated polarised sky in OUT/data, under the
# heavy lock, timed; a .code snapshot of the simulator beside OUT.
set -euo pipefail
W=$HOME/Worktrees/rang/fp-g9-stokes
O=$1; sky=$2; shift 2
mkdir -p "$O/data" "$O.code"
cp "$W/examples/g9_stokes_simulate.py" "$W/examples/gemclean_bench_simulate.py" "$O.code/"
cp -r "$W/research/results/g9-stokes-scripts" "$O.code/"
git -C "$W" rev-parse HEAD > "$O.code/commit"
git -C "$W" status --porcelain > "$O.code/status"
cd "$W"
rm -rf "$O/data/$sky.ms"
flock ~/.rang-heavy.lock /usr/bin/time -f "SIM $sky %e s %M KB" .venv/bin/python examples/g9_stokes_simulate.py \
  "$O/data/$sky.ms" --sky "$sky" --catalogue "$O/data/$sky.json" "$@"
