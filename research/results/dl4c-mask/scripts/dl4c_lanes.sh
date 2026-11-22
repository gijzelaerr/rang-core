#!/bin/bash
# DL4c stage 6 A-arm lanes (research/dl4c-mask.md section 9, step 3); at most 20 slots held.
R=$HOME/rang-data/outputs/dl4c-mask-20261120
D=$(dirname "$0")/dl4c.sh
waitfor() { until [ -e "$1" ]; do sleep 60; done; }
lane1() { bash $D image R1 A; bash $D image R3 A; waitfor $R/sim/T2/done; bash $D image T2 A; }
lane2() { bash $D image R2 A; waitfor $R/sim/T1/done; bash $D image T1 A; waitfor $R/sim/T3/done; bash $D image T3 A; }
lane3() { for c in T1 T2 T3; do bash $D sim $c; done; for c in T1 T2 T3; do bash $D prep $c; done; }
lane1 > $R/logs/lane1.log 2>&1 &
lane2 > $R/logs/lane2.log 2>&1 &
lane3 > $R/logs/lane3.log 2>&1 &
wait
echo "$(date -Is) lanes done" >> $R/logs/driver.log
