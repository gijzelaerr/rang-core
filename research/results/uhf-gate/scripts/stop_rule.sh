#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-gate D attempt 1: research/uhf-gate.md section 3 stop rule. calibrate started
# 2026-11-27T06:33:47Z; if its model step is not done 12 h later (2026-11-27T18:33:47Z =
# 20:33:47 SAST), stop the rang run process only (not the wrappers), before any solution is read.
D=$HOME/rang-data/outputs/uhf-gate-20261126/D
P=3773031
LOG=$D/R/stop-rule.log
DEADLINE=$(date -d 2026-11-27T18:33:47Z +%s)
echo "$(date -Is) armed: pid $P, deadline $(date -d @$DEADLINE -Is)" >> $LOG
while [ $(date +%s) -lt $DEADLINE ]; do
  kill -0 $P 2>/dev/null || { echo "$(date -Is) pid $P gone before the deadline; nothing done" >> $LOG; exit 0; }
  sleep 30
done
st=$(python3 -c "import json;print(json.load(open(\"$D/1752418159.ms.rang-run/state.json\"))[\"stages\"][\"calibrate\"][\"status\"])")
nsol=$(find $D/1752418159.ms.rang-run/calibrate -mindepth 1 | wc -l)
echo "$(date -Is) deadline: calibrate=$st, entries in rang-run/calibrate: $nsol, io: $(tr "\n" " " < /proc/$P/io | cut -c1-80)" >> $LOG
if [ "$st" = running ] && [ "$nsol" = 0 ] && kill -0 $P 2>/dev/null; then
  kill -TERM $P && echo "$(date -Is) SIGTERM sent to $P (rang-core run): model step not done in 12 h" >> $LOG
  sleep 120; kill -0 $P 2>/dev/null && kill -KILL $P && echo "$(date -Is) SIGKILL sent to $P" >> $LOG
else
  echo "$(date -Is) not stopped: the guard did not hold (calibrate $st, $nsol entries)" >> $LOG
fi
