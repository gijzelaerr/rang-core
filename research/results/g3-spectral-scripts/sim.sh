#!/usr/bin/env bash
# sim.sh SKY [--sky-seed X --noise-seed Y]: one simulated spectral sky, under the heavy lock, timed.
set -euo pipefail
W=$HOME/Worktrees/rang/fp-g3-spectral
O=/mnt/d/rang/outputs/20261106-g3-spectral/data
mkdir -p $O
sky=$1; shift
cd $W
rm -rf $O/$sky.ms
flock ~/.rang-heavy.lock /usr/bin/time -f "SIM $sky %e s %M KB" .venv/bin/python examples/g3_spectral_simulate.py $O/$sky.ms --sky $sky --catalogue $O/$sky.json "$@"
