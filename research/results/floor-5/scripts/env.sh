source ~/.rang-env.sh
export OUT=$HOME/rang-data/outputs/floor-5-20261117
export WT=$HOME/Worktrees/rang/floor-5
export RANG_FLOOR_HELD=$OUT/inputs/20261103-gemclean-heldout/real
export PY=$WT/.venv/bin/python  # floor-5 worktree venv (deps = main venv freeze 11:20), rang from $WT/python
export PYTHONPATH=$WT/python  # pinned: floor-5 worktree Python + copied extension ce12e7d2
export LOCK="$PY $HOME/Github/rang/tools/heavy_lock.py"
export RANG_HEAVY_NICE=19
