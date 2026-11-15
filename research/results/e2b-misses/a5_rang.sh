#!/bin/bash
# Arm A4's GeMClean side on Windows (research/e2b-misses.md 9.18; a4_rang.sh with 9.18 paths), run from
# Git Bash; the caller wraps it in the main checkout's heavy_lock.py.
#   a4_rang.sh FID TAG EPS    -> D:/rang/outputs/e2b-close-20261115/a5/rang/TAG-eps<EPS>
set -u
fid=$1; tag=$2; eps=$3
P=D:/rang/outputs/e2b-close-20261115/a5
WT=C:/Users/gijsm/Worktrees/rang/e2b-close
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
out=$P/rang/$tag-eps$eps
mkdir -p "$out"
s=$(date +%s)
PYTHONPATH=$WT/python "$PY" -m rang.gemclean -name "$out/image" -size 2048 2048 -scale 2asec \
  -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
  -data-column RANG_CORRECTED_DATA -wgridder-accuracy "$eps" -niter 0 -field "$fid" \
  -scans 17,18,19,20 -unit-weights -no-update-model-required -j 4 \
  D:/rang/outputs/e2-20261111-20-e2b/casa/e2b.ms > "$P/rang/$tag-eps$eps.out" 2>&1
rc=$?
echo "$(date -Is) rang $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
