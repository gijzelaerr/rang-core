# sdm03-default (research/sdm03-default.md) environment on nash
source ~/.rang-env.sh
export F5=$HOME/rang-data/outputs/floor-5-20261117
export F6=$HOME/rang-data/outputs/floor-6-20261117
export HELD=$F5/inputs/20261103-gemclean-heldout/real   # the pilot folder: cal2.ms, set A's mask (read only)
export MASK=$HELD/images/source-mask.fits
export E2A=$HOME/rang-data/e2-a/ESO137/ms1_target.zarr  # subtables linked from here (read only)
export OUT=$HOME/rang-data/outputs/sdm03-default-20261118
export Z=$OUT/inputs/ms1_target.zarr                    # the reserve groups, fetched here
export LOGS=$OUT/logs RUN=$OUT/run
export WT=$HOME/Worktrees/rang/sdm03-default
export PY=$WT/.venv/bin/python
export SD=$WT/examples/sdm03_default.py
export G3=$WT/examples/g3_spectral_simulate.py
export P1=$WT/research/results/floor-3/p1.yaml
export B=$HOME/Build/tmp/20261118-sdm03
export LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
export RANG_HEAVY_NICE=19
export CAP=16   # slots this driver books at most
