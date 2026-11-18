# automask-cycle (research/automask-cycle.md) environment on nash
source ~/.rang-env.sh
export OUT=$HOME/rang-data/outputs/automask-cycle-20261118
export HELD=$OUT/inputs/held                    # copy of floor-5 pilot folder: cal2.ms, set A mask, pilot model
export MASK=$HELD/images/source-mask.fits
export E2A=$HOME/rang-data/e2-a/ESO137/ms1_target.zarr  # subtables linked from here (read only)
export Z=$OUT/inputs/ms1_target.zarr
export LOGS=$OUT/logs RUN=$OUT/run
export WT=$HOME/Worktrees/rang/automask-cycle-state     # c3d6bf72 (Rust of aef6c48c), sdm03 driver
export PY=$WT/.venv/bin/python
export SD=$WT/examples/sdm03_default.py
export P1=$WT/research/results/floor-3/p1.yaml
export LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
export RANG_HEAVY_NICE=19
