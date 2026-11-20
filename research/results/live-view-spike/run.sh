#!/bin/bash
# Spike capture (research/live-view-scope.md section 7): S2, hook off then on.
out=/d/rang/outputs/20261120-liveview-spike
bin=/c/Users/gijsm/Worktrees/rang/live-view-spike/core/target/release/gemclean.exe
ms='D:\rang\data\20261102-gemclean-bench-sims\s2.ms'
export RAYON_NUM_THREADS=4
for arm in off on; do
  if [ $arm = on ]; then export RANG_RECORD_DIR="D:\rang\outputs\20261120-liveview-spike\on\record"; else unset RANG_RECORD_DIR; fi
  s=$(date +%s.%N)
  (cd $out/$arm && $bin -name img -size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -mgain 0.8 -auto-threshold 3.0 -auto-mask 5.0 -multiscale -data-column DATA -field 0 -no-update-model-required "$ms" > gemclean.log 2>&1; echo "exit $?" >> gemclean.log)
  e=$(date +%s.%N); echo "$arm wall $(echo "$e - $s" | bc) s"
done
cd $out && sha256sum on/*.fits off/*.fits
