#!/bin/bash
# DL4c amendment 2: the six A images again with -multiscale-max-scales 9, two lanes
# (the two-job gate in dl4c.sh holds the cap). The 10-scale R1-A and R2-A are kept as
# img/R1-A10 and img/R2-A10.
R=$HOME/rang-data/outputs/dl4c-mask-20261120
D=$(dirname "$0")/dl4c.sh
cd "$R/img"
for c in R1 R2; do [ -d "$c-A" ] && [ ! -e "$c-A10" ] && mv "$c-A" "$c-A10"; done
for c in R3 T1 T2 T3; do [ -d "$c-A" ] && [ ! -e "$c-A/done" ] && mv "$c-A" "$c-A-failed10"; done
lane1() { bash $D image R1 A; bash $D image R3 A; bash $D image T2 A; }
lane2() { bash $D image R2 A; bash $D image T1 A; bash $D image T3 A; }
lane1 > $R/logs/lane2-1.log 2>&1 &
lane2 > $R/logs/lane2-2.log 2>&1 &
wait
echo "$(date -Is) lanes2 done" >> $R/logs/driver.log
