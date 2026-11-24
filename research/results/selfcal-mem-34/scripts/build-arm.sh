#!/bin/bash
# selfcal-mem-34 on nash: venv and release extension of the worktree.
set -euo pipefail
source ~/.rang-env.sh
W=~/Build/tmp/20261124-selfcal-mem-34/arm
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
cd $W
[ -x .venv/bin/python ] || uv venv -q .venv
VIRTUAL_ENV=$W/.venv uv pip install -q maturin numpy pyyaml astropy pytest scipy
$LOCK run --slots 8 --mem 8 -- nice -n 19 ionice -c3 env CARGO_BUILD_JOBS=8 VIRTUAL_ENV=$W/.venv /usr/bin/time -f "build %e s %M KB" $W/.venv/bin/maturin develop --release -q
