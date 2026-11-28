#!/usr/bin/env bash
R=D:/rang/outputs/dd14-20261127
until grep -q PREP_OK $R/times.log; do
  if grep -q "rc=[1-9]" $R/times.log; then echo PREP_FAILED; exit 1; fi
  sleep 30
done
bash $R/scripts/lane.sh Q12 QP12 AX > $R/logs/laneA.out 2>&1 &
sleep 120
bash $R/scripts/lane.sh AT12 ATP12 QPN12 > $R/logs/laneB.out 2>&1 &
wait
echo LANES_DONE >> $R/times.log
