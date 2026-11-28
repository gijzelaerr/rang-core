#!/bin/sh
# SPDX-License-Identifier: MIT
# P2 (dirty, 6144^2) and P2b (clean, 3072^2) of research/gate3c-averaging.md on
# glacier with the branch's gemclean. Usage: p2_run.sh OUTROOT PYTHON
O=$1; PY=$2
export RAYON_NUM_THREADS=8
G="-weight briggs 0.5 -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -data-column DATA -unit-weights -no-update-model-required"
for n in 1 2 4; do
  s=$(date +%s)
  $PY -m rang.gemclean -name $O/p2/dirty-n$n -size 6144 6144 -scale 2asec -niter 0 $G -average-channels $n $O/p2/p2.ms > $O/p2/dirty-n$n.out 2>&1
  echo "p2 dirty n$n rc $? $(( $(date +%s)-s )) s"
done
for n in 1 2; do
  s=$(date +%s)
  $PY -m rang.gemclean -name $O/p2b/clean-n$n -size 3072 3072 -scale 2asec -niter 200000 -mgain 0.9 -threshold 1e-4 -auto-mask 5.0 -multiscale -fit-spectral-pol 2 $G -average-channels $n $O/p2b/p2b.ms > $O/p2b/clean-n$n.out 2>&1
  echo "p2b clean n$n rc $? $(( $(date +%s)-s )) s"
done
