#!/bin/bash
# QuartiCal solves on scan 9: versions x weight arms. complex G, 2 x 32 intervals, 1e-7, fraction 0.99, cap 100.
set -u
B=~/Build/tmp/20261030-q452
cd $B/solve
export OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=4
run() { # name venv ms weightarg extra...
  local name=$1 v=$2 ms=$3 warg=$4; shift 4
  rm -rf out/$name
  NUMBA_CACHE_DIR=$B/nc-solve-$v /usr/bin/time -f "$name wall %e s rss %M KB" $B/$v/bin/goquartical \
    input_ms.path=$ms input_ms.data_column=DATA $warg input_model.recipe=MODEL_DATA \
    solver.terms=[G] G.type=complex G.time_interval=2 G.freq_interval=32 solver.threads=4 \
    output.gain_directory=out/$name/gains.qc output.log_directory=out/$name/logs output.flags=false "$@" \
    > logs/$name.log 2>&1
  echo "$name exit $? $(tail -1 logs/$name.log)"
}
mkdir -p logs out
for warm in venv027 venvpre venv; do :; done
for w in unit native x4; do
  case $w in unit) ms=scan9.ms; warg="input_ms.weight_column=";;
             native) ms=scan9.ms; warg=input_ms.weight_column=WEIGHT_SPECTRUM;;
             x4) ms=scan9w.ms; warg=input_ms.weight_column=WEIGHT_SPECTRUM;; esac
  C="solver.convergence_criteria=1e-7 solver.iter_recipe=[100] solver.convergence_fraction=0.99"
  run $w-027 venv027 $ms "$warg" $C
  run $w-pre venvpre $ms "$warg" $C G.referenced=false
  run $w-post venv $ms "$warg" $C G.referenced=false
  run $w-postref venv $ms "$warg" $C
  run $w-ref venv $ms "$warg" solver.convergence_criteria=1e-7 solver.iter_recipe=[500] solver.convergence_fraction=2.0 G.referenced=false
done
echo solves-done
