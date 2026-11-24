#!/bin/bash


cd /home/gijs/rang-data/outputs/gate3c-rerun-20261123
SCRIPTS=$HOME/Github/rang/research/results/e2-acceptance-scripts LEG=e2n MS=/home/gijs/rang-data/outputs/gate3c-rerun-20261123/e2n.ms R=/home/gijs/rang-data/outputs/gate3c-rerun-20261123 PY=$HOME/Github/rang/.venv/bin/python LEGPY=$HOME/Build/tmp/20261123-gate3c-rerun/e2n-venv/bin/python LOCK=$HOME/Github/rang/tools/heavy_lock.py SELFCAL_VERSION=flags.rang_selfcal_20261117T072854Z CLEAN=1 DARM=1 bash $HOME/Worktrees/rang/gate3c-rerun/research/results/gate3c-rerun/chain.sh
