#!/bin/bash
# QuartiCal 0.2.7 complex-term convergence sweep on scan 9: iter_recipe=[k], stop fraction 1.0.
# usage: sweep.sh <setting> <time_interval> <freq_interval> <criterion>
set -u
S=$(cd "$(dirname "$0")" && pwd)
B=~/Build/tmp/20261030-upstream-prs/conv
cd $B
export NUMBA_CACHE_DIR=$B/numba-cache
name=$1; ti=$2; fi=$3; crit=$4
run() {  # label iters fraction
  /usr/bin/time -f "$name $1 wall %e s maxrss %M KB" ../venv-qc027/bin/goquartical input_ms.path=scan9.ms \
    input_ms.data_column=DATA input_model.recipe=MODEL_DATA solver.terms=[G] G.type=complex \
    G.time_interval=$ti G.freq_interval=$fi solver.convergence_criteria=$crit \
    solver.iter_recipe=[$2] solver.convergence_fraction=$3 \
    output.gain_directory=$name/$1/gains.qc output.log_directory=$name/$1/logs.qc output.flags=false \
    > $name-$1.log 2>&1
  tail -1 $name-$1.log
}
mkdir -p $name
run default 25 0.99
for k in 1 2 3 4 6 8 10 12 15 20 25 35 50 75 100; do run k$k $k 1.0; done
../venv-qc027/bin/python "$S/analyse.py" $name $ti $fi > $name.json
