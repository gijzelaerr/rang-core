#!/bin/bash
# A2's scores, each case as soon as its tables exist (Windows venv, 4 rayon threads).
# Run under the main checkout's heavy_lock.py --slots 4 by the caller.
export RAYON_NUM_THREADS=4
PY=C:/Users/gijsm/Worktrees/rang/e2b-arms/.venv/Scripts/python.exe
S=C:/Users/gijsm/Worktrees/rang/e2b-arms/research/results/e2b-misses
O='D:\rang\outputs\e2b-arms-20261114\a2'
t() { s=$(date +%s); "$@"; echo "rc=$? secs=$(( $(date +%s)-s )) :: $*"; }
[ -s "/d/rang/outputs/e2b-arms-20261114/a2/c0.json" ] || t $PY $S/a2_score.py control "$O\c0.json"
for n in after-spec match-ones after-ones match-spec; do
  until [ -s "/d/rang/outputs/e2b-arms-20261114/a2/$n/tables/F/table.dat" ] && grep -q '"fluxtable": "/w/'$n'/tables/F"' /d/rang/outputs/e2b-arms-20261114/a2/$n/result.json; do sleep 30; done
  [ -s "/d/rang/outputs/e2b-arms-20261114/a2/$n/score.json" ] || t $PY $S/a2_score.py case "$O\$n\tables" "$O\$n\score.json"
done
t $PY $S/a2_summary.py "$O"
