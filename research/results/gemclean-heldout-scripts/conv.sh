#!/usr/bin/env bash
set -uo pipefail
W=/home/gijsm/Worktrees/rang/gemclean-heldout
R=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
Z=/mnt/d/rang/data/eso137-pilot/ESO137/ms1_target.zarr
mkdir -p $R
cd /tmp
py="nice -n 5 $W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
/usr/bin/time -f "convert %e s %M kB" $py convert $Z $R/raw.ms
/usr/bin/time -f "verify %e s %M kB" $py verify $Z $R/raw.ms $R/verify.json
echo CONV-DONE
