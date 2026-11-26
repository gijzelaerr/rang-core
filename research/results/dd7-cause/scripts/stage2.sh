#!/usr/bin/env bash
# stage 2 (research/dd7-cause.md section 6), two lanes, in A2's rank order; R1, R1c, I0-pin run in their own lane
R=D:/rang/outputs/dd7-20261125; L=$R/scripts/lane.sh; B=$R/b/sky.npy; RM=$R/models/RM.npy
g() { echo "$1|4|15|dd7.py grid $R/$2 4 $3 $R/grid/$1.json $4"; }
b() { echo "build-$1|${2:-2}|${3:-10}|dd7.py build $R $1"; }
bash $L "$(b T0)" "$(g T0-free T0 $B --free)" "$(b TSa)" "$(g TSa TSa $B --free)" "$(b T1)" "$(g T1 T1 $B --free)" \
  "$(g R2 real $R/models/DEEP.npy --free)" "$(b T2)" "$(g T2 T2 $B --free)" "$(b T3)" "$(g T3 T3 $B --free)" &
{ until grep -q "^build-T0 end .* rc=0" $R/times.log; do sleep 20; done; bash $L "$(g T0-pin T0 $B)" "$(b TSb)" "$(g TSb TSb $B --free)" \
  "$(g I0-free I0 $B --free)" "$(b R3 4 15)" "$(g R3 R3 $RM --free)" "$(b T4)" "$(g T4 T4 $B --free)"; } &
wait
bash $L "L2000|4|15|dd7.py grid $R/real 4 $RM $R/grid/L2000.json --free --cap 2000"
