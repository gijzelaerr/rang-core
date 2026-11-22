#!/bin/bash
# DL4a (#41) baseline: the pilot (four correlations) and one rang-core selfcal run at the
# defaults (selfcal-defaults run D), to give the round models (research/dl4a-screen.md section 4).
set -eu
source ~/.rang-env.sh
R=~/rang-data/outputs/dl4a-screen-20261120
W=~/Worktrees/rang/dl4a-screen
PY=$W/.venv/bin/python
export RANG_FLOOR_HELD=$R/src RAYON_NUM_THREADS=8 PATH=$W/.venv/bin:$PATH
cd $W
mkdir -p $R/done $R/logs
[ -e $R/done/base.done ] || { /usr/bin/time -f "base %e s %M KB" nice -n 19 ionice -c3 $PY examples/selfcal_grid.py base --out $R; touch $R/done/base.done; }
[ -e $R/done/prepare.done ] || { /usr/bin/time -f "prepare %e s %M KB" nice -n 19 ionice -c3 $PY examples/selfcal_grid.py prepare D --out $R; touch $R/done/prepare.done; }
[ -e $R/done/selfcal.done ] || { /usr/bin/time -f "selfcal %e s %M KB" nice -n 19 ionice -c3 rang-core selfcal $R/D/config.yaml $R/D/pilot.ms --run-dir $R/D/run; touch $R/done/selfcal.done; }
echo "baseline done $(date -u +%FT%TZ)"
