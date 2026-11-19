#!/bin/bash
# rebuild.sh GROUP: sdm03-default real_track stages up to state (no arms), in this run root
source ~/Build/tmp/20261118-automask-cycle/env.sh
mkdir -p $RUN $LOGS
launch(){ local name=$1 n=$2 mem=$3 rc; shift 3
  [ -f $LOGS/$name.ok ] && return 0
  echo "$(date -Is) start $name" >> $LOGS/driver.log
  $LOCK run --slots $n --mem $mem -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=$n OMP_NUM_THREADS=$n OPENBLAS_NUM_THREADS=$n MKL_NUM_THREADS=$n /usr/bin/time -f "TIME $name %e s %M KB" "$@" >> $LOGS/$name.log 2>&1
  rc=$?; [ $rc -eq 0 ] && touch $LOGS/$name.ok
  printf "%s\t%s\t%s\t%s\t%s\n" "$name" "$n" "$mem" "$rc" "$(grep "^TIME" $LOGS/$name.log | tail -1)" >> $OUT/timing.tsv
  echo "$(date -Is) end $name rc $rc" >> $LOGS/driver.log; return $rc; }
g=$1; r=$OUT/r-$g
launch fetchmeta-$g 1 2 $PY $SD fetchms --group $g --root $Z --src $E2A --phase meta || exit 1
launch meta-$g 1 4 $PY $SD real --group $g -- meta --out $r --held $HELD --zarr $Z || exit 1
launch gains-$g 1 4 $PY $SD real --group $g -- fetch --out $r --held $HELD --zarr $Z --gains $r/gains || exit 1
launch fetchdata-$g 2 4 $PY $SD fetchms --group $g --root $Z --src $E2A --phase data || exit 1
launch build-$g 1 12 $PY $SD real --group $g -- build --out $r --held $HELD --zarr $Z --gains $r/gains || exit 1
launch copy-$g 1 6 $PY $SD real --group $g -- copy --out $r --held $HELD || exit 1
launch selfcal-$g 8 32 $PY -m rang.core_cli selfcal $P1 $r/P/pilot.ms --run-dir $r/P/run || exit 1
launch state-$g 4 16 $PY $SD real --group $g -- state --out $r --held $HELD --cal2 $r/build/cal2.ms --g1 $r --ms4 $r/P/pilot.ms || exit 1
echo "$(date -Is) REBUILD $g DONE" >> $LOGS/driver.log
