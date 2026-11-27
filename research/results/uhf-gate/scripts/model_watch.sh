#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-gate D: log the rang run process IO and calibrate status every 10 min (section 3 stop rule watch)
D=$HOME/rang-data/outputs/uhf-gate-20261126/D
P=$1
while kill -0 $P 2>/dev/null; do
  st=$(python3 -c "import json;s=json.load(open(\"$D/1752418159.ms.rang-run/state.json\"))[\"stages\"];print(\" \".join(f\"{k}={v[\"status\"]}\" for k,v in s.items()))" 2>/dev/null)
  io=$(awk "/rchar|wchar/{printf \"%s %.1fGB \", \$1, \$2/1e9}" /proc/$P/io)
  cpu=$(ps -o pcpu=,etime= -p $P)
  new=$(ls -t --time-style=+%H:%M $D/1752418159.ms | sed -n 2p | awk "{print \$6, \$7}")
  echo "$(date -Is) $st | $io | cpu $cpu | newest $new" >> $D/R/model-watch.log
  grep -q "calibrate=done" <<< "$st" && break
  sleep 600
done
