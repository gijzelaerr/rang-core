#!/bin/bash
# SPDX-License-Identifier: MIT
# research/e2a-kzero.md on nash, the whole reading: the two arm chains (zs, zsd;
# kz_chain.sh, 4 slots each) and the calibrate-level phase (kz_3b.sh, day window
# only) at once; every 30 min the status file is rewritten from the logs.
# Launch detached:  setsid nohup bash drive.sh > O/drive.log 2>&1 < /dev/null &
# The last line of O/drive.log is "ALL DONE zs=RC zsd=RC 3b=RC" when it ends.
# A fresh agent: read O/drive.log, O/{zs,zsd}/R/chain-steps.log, O/3b-steps.log;
# a failed part is rerun from its step with `bash kz_chain.sh ARM STEP` or
# `bash kz_3b.sh STEP`; the readings are O/score-kz.json and O/{zs,zsd}/R/*.json.
set -u
N=$(cd "$(dirname "$0")" && pwd)
O=$HOME/rang-data/outputs/e2a-kzero-20261117
STATUS=$HOME/Github/rang/outputs/status/e2a-kzero.md
echo "$(date -Is) drive start $(cd "$N" && git rev-parse HEAD)"
bash "$N/kz_chain.sh" zs > "$O/chain-zs.log" 2>&1 & pz=$!
bash "$N/kz_chain.sh" zsd > "$O/chain-zsd.log" 2>&1 & pd=$!
bash "$N/kz_3b.sh" > "$O/3b.log" 2>&1 & p3=$!
status() {
  {
    echo "# e2a-kzero (status, written by drive.sh on nash)"
    echo
    echo "- $(TZ=Africa/Johannesburg date '+%Y-%m-%d %H:%M') SAST. Driver $O/drive.log; branch e2a-kzero."
    for a in zs zsd; do
      echo "- $a: $(tail -1 "$O/$a/R/chain-steps.log" 2>/dev/null || echo 'not started')"
    done
    echo "- 3b: $(grep -v '^heavy_lock' "$O/3b-steps.log" 2>/dev/null | tail -1 || echo 'not started')"
    echo "- lock: $(python3 "$HOME/Github/rang/tools/heavy_lock.py" status 2>/dev/null | sed -n 2p)"
  } > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}
while kill -0 $pz 2>/dev/null || kill -0 $pd 2>/dev/null || kill -0 $p3 2>/dev/null; do
  status
  for _ in $(seq 180); do
    kill -0 $pz 2>/dev/null || kill -0 $pd 2>/dev/null || kill -0 $p3 2>/dev/null || break
    sleep 10
  done
done
wait $pz; rz=$?
wait $pd; rd=$?
wait $p3; r3=$?
status
echo "$(date -Is) ALL DONE zs=$rz zsd=$rd 3b=$r3"
