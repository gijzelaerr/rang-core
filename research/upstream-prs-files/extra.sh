#!/bin/bash
# k+1 runs for the one-iteration analysis, then onestep.py.
set -u
S=$(cd "$(dirname "$0")" && pwd)
B=~/Build/tmp/20261030-upstream-prs/conv
cd $B
export NUMBA_CACHE_DIR=$B/numba-cache
one() {  # name ti fi crit k
  /usr/bin/time -f "$1 k$5 wall %e s maxrss %M KB" ../venv-qc027/bin/goquartical input_ms.path=scan9.ms \
    input_ms.data_column=DATA input_model.recipe=MODEL_DATA solver.terms=[G] G.type=complex \
    G.time_interval=$2 G.freq_interval=$3 solver.convergence_criteria=$4 \
    solver.iter_recipe=[$5] solver.convergence_fraction=1.0 \
    output.gain_directory=$1/k$5/gains.qc output.log_directory=$1/k$5/logs.qc output.flags=false > $1-k$5.log 2>&1
  tail -1 $1-k$5.log
}
one defaults 1 1 1e-6 26
one defaults 1 1 1e-6 51
one t2f32 2 32 1e-7 26
one t2f32 2 32 1e-7 51
for k in 25 50; do
  ../venv-qc027/bin/python "$S/onestep.py" defaults $k 1e-6
  ../venv-qc027/bin/python "$S/onestep.py" t2f32 $k 1e-7
done > onestep.jsonl
cat onestep.jsonl
