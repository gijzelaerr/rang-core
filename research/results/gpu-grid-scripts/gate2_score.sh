#!/usr/bin/env bash
# Gate 2 scoring: the CPU (Gate 0 baseline) and GPU runs of every sky and form through
# examples/gemclean_bench_compare.py score. Usage: gate2_score.sh PYTHON
PY=$1
W=/c/Users/gijsm/Worktrees/rang/gpu-grid
O=D:/rang/outputs/20261116-gpu-grid
B=D:/rang/outputs/20261102-gemclean/bench
H=D:/rang/outputs/20261103-gemclean-heldout/sim
for sky in ${SKIES:-s1 s2 s3 h1 h2 h3 h4}; do
  case $sky in s*) P=$B/prep/$sky; C=$B/data/$sky.json ;; *) P=D:/rang/outputs/20261104-speed/prep-h/$sky; C=$H/data/$sky.json ;; esac
  R=$O/gate2/score/$sky; mkdir -p $R
  for form in coarse fine; do
    for k in model residual image; do
      cp $O/base/$sky-$form-$k.fits $R/$sky-$form-cpu-$k.fits
      cp $O/gate2/gpu/$sky-$form-$k.fits $R/$sky-$form-gpu-$k.fits
    done
    cp $O/base/$sky-$form.log $R/$sky-$form-cpu.log; cp $O/gate2/gpu/$sky-$form.log $R/$sky-$form-gpu.log
  done
  (cd $W && "$PY" examples/gemclean_bench_compare.py score $P $C $R $O/gate2/score/$sky.json \
     --jobs $sky-coarse-cpu $sky-coarse-gpu $sky-fine-cpu $sky-fine-gpu) > $O/gate2/score/$sky.out 2>&1
  echo "$sky scored rc $?"
done
