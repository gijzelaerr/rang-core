# floor-6 (research/floor-6.md) environment on nash
source ~/.rang-env.sh
export F5=$HOME/rang-data/outputs/floor-5-20261117
export HELD=$F5/inputs/20261103-gemclean-heldout/real   # the pilot folder: cal2.ms, set A's mask, pilot model (read only)
export OUT=$HOME/rang-data/outputs/floor-6-20261117
export HO=$OUT/ho PI=$OUT/pilot FAM=$OUT/family2 GAINS=$OUT/inputs/gains LOGS=$OUT/logs
export WT=$HOME/Worktrees/rang/floor-6
export PY=$WT/.venv/bin/python   # floor-6 venv, freeze equal to floor-5's
export PYTHONPATH=$WT/python     # pinned: floor-6 Python + floor-5's extension ce12e7d2 (copied)
export S6=$WT/examples/floor6_tests.py
export B=$HOME/Build/tmp/20261117-floor6
export LOCK="$PY $HOME/Github/rang/tools/heavy_lock.py"
export RANG_HEAVY_NICE=19
