#!/bin/bash
# Arm A5's GeMClean side on Windows (research/e2b-misses.md 9.18), run from
# Git Bash; the caller wraps it in the main checkout's heavy_lock.py.
#   a5_rang.sh e2b FID TAG   gate 3c's settings + -auto-mask 5 -> $P/rang-mask/TAG
#   a5_rang.sh m0            M0 on G9's P1                     -> $P/m0/rang
set -u
P=D:/rang/outputs/gemclean-iquv-mask-20261115
WT=C:/Users/gijsm/Worktrees/rang/gemclean-iquv-mask
PY=$WT/.venv/Scripts/python.exe
T=$WT/research/results/e2b-misses/a5_time.py
s=$(date +%s)
case "$1" in
  e2b)
    fid=$2; tag=$3; out=$P/rang-mask/$tag; mkdir -p "$out"
    "$PY" "$T" "$out.time.json" -- "$PY" -m rang.gemclean -name "$out/image" -size 2048 2048 \
      -scale 2asec -weight briggs 0.0 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 \
      -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
      -data-column RANG_CORRECTED_DATA -field "$fid" -scans 17,18,19,20 -unit-weights \
      -no-update-model-required -j 4 $P/e2b-slim.ms \
      > "$out.out" 2>&1
    rc=$? ;;
  m0)
    out=$P/m0/rang; mkdir -p "$out"
    "$PY" "$T" "$out.time.json" -- "$PY" -m rang.gemclean -name "$out/g" -size 2048 2048 \
      -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA \
      -field 0 -wgridder-accuracy 1e-6 -mgain 0.8 -pol IQUV -join-polarizations -channels-out 8 \
      -join-channels -auto-threshold 3 -auto-mask 5 -no-update-model-required -j 4 \
      D:/rang/outputs/g9-20261107-02/data/P1.ms > "$out.out" 2>&1
    rc=$? ;;
esac
echo "$(date -Is) rang $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
