#!/bin/bash
# e2b-misses 9.28's GeMClean arm on Windows (Git Bash), this worktree's build; the
# caller wraps it in the main checkout's heavy_lock.py.
#   c3_rang.sh dirty|clean FID TAG   gate 3c's settings, reading D:/.../f<FID>.ms
set -u
m=$1; fid=$2; tag=$3
P=D:/rang/outputs/e2b-confirm-20261116
WT=C:/Users/gijsm/Worktrees/rang/e2b-confirm
PY=$WT/.venv/Scripts/python.exe
T=$WT/research/results/e2b-misses/a5-mask/a5_time.py
out=$P/rang-$m/$tag; mkdir -p "$out"
if [ "$m" = dirty ]; then
  extra="-niter 0 -wgridder-accuracy 1e-06"
else
  extra="-niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001"
fi
s=$(date +%s)
"$PY" "$T" "$out.time.json" -- "$PY" -m rang.gemclean -name "$out/image" -size 2048 2048 \
  -scale 2asec -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
  -data-column E2C_RANG_CORRECTED_DATA -field "$fid" -scans 17,18,19,20 -unit-weights \
  -no-update-model-required -j 4 $extra "$P/f$fid.ms" > "$out.out" 2>&1
rc=$?
echo "$(date -Is) rang $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
