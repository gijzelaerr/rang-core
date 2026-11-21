#!/bin/bash
# DL4c amendment 4: stop R1-A at 24 h of GeMClean wall time (2026-11-22 02:30 SAST) if it is still running.
R=$HOME/rang-data/outputs/dl4c-mask-20261120
deadline=$(date -d "2026-11-22 02:30:10" +%s)
while [ "$(date +%s)" -lt "$deadline" ]; do
  [ -e "$R/img/R1-A/done" ] && { echo "$(date -Is) R1-A ended by itself before the deadline" >> "$R/logs/driver.log"; exit 0; }
  sleep 300
done
pids=$(pgrep -f "python -m rang.gemclean -name $R/img/R1-A/image")
if [ -n "$pids" ]; then
  kill $pids
  echo "$(date -Is) R1-A stopped at the amendment-4 deadline (24 h), not converged" >> "$R/logs/driver.log"
  echo "$(date -Is) R1-A stopped at deadline" >> "$R/logs/FAILED-or-STOPPED"
fi
