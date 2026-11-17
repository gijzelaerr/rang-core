#!/usr/bin/env bash
# df5o_measure.sh : examples/compare_df5o.py measure on each rml-gap DF5-O arm (Windows, Git Bash),
# with DF5-O's floor and P2 (copied to $D/ref); each under the main checkout's heavy_lock
# (4 slots, 4 GB; DF5-O measured 735 MB).
set -u
W=$(cd "$(dirname "$0")/../../.." && pwd)
PY=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
D=D:/rang/outputs/rml-gap-20261113/df5o
mkdir -p $D/measures
for a in ws-G ws-Gd ws-W pfb-sara-U-a; do
  t=$(date +%s)
  RAYON_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 $PY C:/Users/gijsm/Github/rang/tools/heavy_lock.py     run --slots 4 --mem 4 -- $PY "$W/examples/compare_df5o.py" measure $D/field $D/$a-r1 $D/measures/$a.json \
    --floor $D/ref/floor.json --p2 $D/ref/p2.json >$D/measures/$a.log 2>&1
  echo "$a rc=$? wall=$(($(date +%s) - t))s"
done
