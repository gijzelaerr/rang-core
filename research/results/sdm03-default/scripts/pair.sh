#!/bin/bash
# pair.sh TAG ARM_A ARM_B MS STATE: two ESO137 arms at once, 8 threads each, under one 16-slot booking
# (amendment 2: the cost pair shares the host's state); each arm writes its own TIME line and .ok.
source ~/Build/tmp/20261118-sdm03/env.sh
t=$1; a=$2; b=$3; ms=$4; st=$5
one(){
  [ -f $LOGS/arm-$t-$1.ok ] && return 0
  env RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 /usr/bin/time -f "TIME arm-$t-$1 %e s %M KB" \
    $PY $SD image $1 --kind eso --ms $ms --prefix $st/img/$1/image --mask $MASK --column CORRECTED_DATA >> $LOGS/arm-$t-$1.log 2>&1
  local rc=$?
  [ $rc -eq 0 ] && touch $LOGS/arm-$t-$1.ok
  printf '%s\t%s\t%s\t%s\t%s\n' "arm-$t-$1" 8 - "$rc" "$(grep '^TIME' $LOGS/arm-$t-$1.log | tail -1)" >> $OUT/timing.tsv
  return $rc
}
one $a & p1=$!; one $b & p2=$!
wait $p1; r1=$?; wait $p2; r2=$?
exit $(( r1 + r2 ))
