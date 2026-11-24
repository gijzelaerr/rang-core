#!/bin/bash
# selfcal-mem-34: the gemclean binary of the worktree as it is, copied to $O/gemclean-$1.
set -euo pipefail
source ~/.rang-env.sh
W=~/Worktrees/rang/selfcal-mem-34
O=~/rang-data/outputs/selfcal-mem-34-20261124
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
cd $W
$LOCK run --slots 8 --mem 8 -- nice -n 19 ionice -c3 env CARGO_BUILD_JOBS=8 /usr/bin/time -f "bin %e s %M KB" cargo build -q --profile gemclean --bin gemclean --manifest-path core/Cargo.toml
cp core/target/gemclean/gemclean $O/gemclean-$1
echo "$1 $(git rev-parse --short HEAD) $(git diff --stat | tail -1)" >> $O/binaries.txt
