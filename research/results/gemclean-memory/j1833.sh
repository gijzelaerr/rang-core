#!/bin/bash
# GeMClean on J1833-2103 with arm A5's argv (research/e2b-misses.md 9.21,
# a5_rang.sh e2b 2 J1833m2103) for research/gemclean-memory.md step 4, from
# Git Bash; the caller wraps it in the main checkout's heavy_lock.py.
#   j1833.sh TAG RUNNER [extra ...]
#     RUNNER: a gemclean binary, or a python.exe (then `-m rang.gemclean`)
#   -> $P/j1833/TAG/: the images' sha256 (images then deleted), the log,
#      the report and memtime.py's record
set -u
P=D:/rang/outputs/gemclean-memory-20261115
H=$(cd "$(dirname "$0")" && pwd)
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
tag=$1; run=$2; shift 2
out=$P/j1833/$tag; mkdir -p "$out"
case "$run" in *python*) pre=("$run" -m rang.gemclean) ;; *) pre=("$run") ;; esac
s=$(date +%s)
"$PY" "$H/memtime.py" "$out/time.json" -- "${pre[@]}" -name "$out/image" -size 2048 2048 \
  -scale 2asec -weight briggs 0.0 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 \
  -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
  -data-column RANG_CORRECTED_DATA -field 2 -scans 17,18,19,20 -unit-weights \
  -no-update-model-required -j 4 "$@" $P/e2b-slim.ms > "$out/log.txt" 2>&1
rc=$?
(cd "$out" && sha256sum *.fits > fits.sha256 && rm -f *.fits)
echo "$(date -Is) j1833 $tag rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
