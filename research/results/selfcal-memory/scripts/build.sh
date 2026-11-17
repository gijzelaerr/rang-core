#!/bin/bash
# selfcal-memory on nash: build the worktree extension, then the pilot base copy and D prepare.
set -euo pipefail
source ~/.rang-env.sh
W=~/Worktrees/rang/selfcal-memory
PY=$W/.venv/bin/python
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
O=~/rang-data/outputs/selfcal-memory-20261117
export RANG_FLOOR_HELD=$HOME/rang-data/outputs/floor-5-20261117/inputs/20261103-gemclean-heldout/real
mkdir -p $O
cd $W
step=$1
case $step in
  build)
    $LOCK run --slots 8 --mem 8 -- nice -n 19 ionice -c3 env CARGO_BUILD_JOBS=8 RUSTUP_TOOLCHAIN=1.93 VIRTUAL_ENV=$W/.venv /usr/bin/time -f "build %e s %M KB" $W/.venv/bin/maturin develop --release --offline -q ;;
  base)
    $LOCK run --slots 1 --mem 4 -- nice -n 19 ionice -c3 bash -c "/usr/bin/time -f \"base %e s %M KB\" $PY examples/selfcal_grid.py base --out $O && /usr/bin/time -f \"prepare %e s %M KB\" $PY examples/selfcal_grid.py prepare D --out $O" ;;
esac
