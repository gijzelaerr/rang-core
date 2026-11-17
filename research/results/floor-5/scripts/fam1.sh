#!/bin/bash
# Family I of research/floor-5.md: fam1.sh STAGE [ARGS]  (gates | skies | pilot | arm NAME | summary)
source ~/Build/tmp/20261117-floor5/env.sh
export RAYON_NUM_THREADS=${RAYON_NUM_THREADS:-4} OMP_NUM_THREADS=${OMP_NUM_THREADS:-4} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-4}
cd $WT
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) $* start"
/usr/bin/time -f "$* %e s %M KB" $PY examples/floor5_tests.py "$@" --out $OUT/floor-5 --g1 $OUT/inputs/floor-4-20261117/g1
rc=$?
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) $* end rc $rc"
exit $rc
