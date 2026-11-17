#!/bin/bash
# G1: floor-3 arm P rerun on nash (floor3_score stages; p1.yaml), for floor-5
source ~/Build/tmp/20261117-floor5/env.sh
cd $WT
t() { local n=$1; shift; local s=$(date +%s.%N); /usr/bin/time -f "$n %e s %M KB" "$@"; echo "$n wall $(echo "$(date +%s.%N) - $s" | bc) s"; }
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) g1 start"
export RAYON_NUM_THREADS=8
t copy $PY ~/Build/tmp/20261117-floor5/f3wrap.py copy P --out $OUT/g1 || exit 1
t g0 $PY ~/Build/tmp/20261117-floor5/f3wrap.py g0 --out $OUT/g1 || exit 1
t selfcal $PY -m rang.core_cli selfcal research/results/floor-3/p1.yaml $OUT/g1/P/pilot.ms --run-dir $OUT/g1/P/run || exit 1
t score $PY ~/Build/tmp/20261117-floor5/f3wrap.py score P --out $OUT/g1 || exit 1
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) g1 end"
