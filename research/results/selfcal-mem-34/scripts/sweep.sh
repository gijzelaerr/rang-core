#!/bin/bash
set -euo pipefail
source ~/.rang-env.sh
O=~/rang-data/outputs/selfcal-mem-34-20261124
A=~/Build/tmp/20261124-selfcal-mem-34/arm
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
$LOCK run --slots 2 --mem 4 -- nice -n 19 ionice -c3 /usr/bin/time -f "sweep %e s %M KB" ~/Worktrees/rang/selfcal-mem-34/.venv/bin/python $A/research/results/selfcal-mem-34/sweep.py $O/gemclean-main $O/gemclean-arm $O/sweep
