#!/bin/bash
# Arm A4's queue (research/e2b-misses.md 9.9).
#   a4_queue.sh wsl       (in WSL) unit on, then C6 and the 9 WSClean runs, one at a time
#   a4_queue.sh windows   (Git Bash) waits for unit-on.json, then C6 and the 9 GeMClean runs
#   a4_queue.sh off       (in WSL) unit off, after both queues ended
set -u
S=$(cd "$(dirname "$0")" && pwd)
RUNS="2:J1833m2103:0.0001"
for e in 1e-05 1e-06 1e-07; do
  RUNS="$RUNS 0:J1331p3030:$e 1:J1939m6342:$e 2:J1833m2103:$e"
done
case "$1" in
  wsl)
    L=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
    P=/mnt/d/rang/outputs/e2b-pastro-20261114/a4
    python3 $L run --slots 1 --mem 2 -- bash "$S/a4_run.sh" unit on || exit 1
    for r in $RUNS; do
      IFS=: read -r fid tag eps <<< "$r"
      python3 $L run --slots 4 --mem 10 -- bash "$S/a4_run.sh" wsclean "$fid" "$tag" "$eps"
    done
    touch "$P/wsclean.done" ;;
  windows)
    L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
    PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
    P=D:/rang/outputs/e2b-pastro-20261114/a4
    until [ -f "$P/unit-on.json" ]; do sleep 30; done
    for r in $RUNS; do
      IFS=: read -r fid tag eps <<< "$r"
      "$PY" $L run --slots 4 --mem 16 -- bash "$S/a4_rang.sh" "$fid" "$tag" "$eps"
    done
    touch "$P/rang.done" ;;
  off)
    python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 1 --mem 2 -- \
      bash "$S/a4_run.sh" unit off ;;
esac
