#!/bin/bash
set -u
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/q452
B=~/Build/tmp/20261030-q452
mkdir -p $B/rang && cd $B/rang
$B/venv027/bin/python -I $S/ms2npz.py $B/solve/scan9.ms unit.npz unit
$B/venv027/bin/python -I $S/ms2npz.py $B/solve/scan9.ms native.npz native
$B/venv027/bin/python -I $S/ms2npz.py $B/solve/scan9w.ms x4.npz native
export RAYON_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1
P=~/Github/rang/.venv/bin/python
for w in unit native x4; do
  for q in archived transposed; do
    RANG_SOLVE_OPTIONS=qp_weights=$q $P -I $S/rangsolve.py $w.npz $w-$q.npz 100 0.99
    RANG_SOLVE_OPTIONS=qp_weights=$q $P -I $S/rangsolve.py $w.npz $w-$q-ref.npz 500 2.0
  done
done
