#!/bin/bash
# Gate 3c dirty with WSClean -no-small-inversion on the three fields at eps
# 1e-4 (research/e2b-misses.md 9.17), in WSL; each step under heavy_lock.
set -u
S=$(cd "$(dirname "$0")" && pwd)
L=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
python3 $L run --slots 1 --mem 2 -- bash "$S/a4_run.sh" unit on || exit 1
rc=0
for r in 2:J1833m2103 1:J1939m6342 0:J1331p3030; do
  IFS=: read -r fid tag <<< "$r"
  python3 $L run --slots 4 --mem 10 -- bash "$S/a4_run.sh" wsclean-nosi "$fid" "$tag" 0.0001 || rc=1
done
python3 $L run --slots 1 --mem 2 -- bash "$S/a4_run.sh" unit off
exit $rc
