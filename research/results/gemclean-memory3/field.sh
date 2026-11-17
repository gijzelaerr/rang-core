#!/bin/bash
# research/gemclean-memory3.md (from gemclean-memory2's): GeMClean on one rebuilt E2-B field with arm A5's
# argv (e2b-misses c3/c3_rang.sh clean, 9.28), from Git Bash; the caller wraps
# it in the main checkout's heavy_lock.py.
#   field.sh FID TAG RUNNER [extra ...]
#     FID 0 J1331+3030, 1 J1939-6342, 2 J1833-2103
#     RUNNER: a gemclean binary, or a python.exe (then `-m rang.gemclean`)
#     KEEP=1 in the environment keeps the FITS files (else deleted after hashing)
#   -> $P/runs/<field>/<TAG>/: fits.sha256, log.txt, the report, memtime.py's time.json
set -u
P=D:/rang/outputs/gemclean-memory3-20261117
IN=D:/rang/outputs/gemclean-memory2-20261116
H=$(cd "$(dirname "$0")" && pwd -W)
PY=C:/Users/gijsm/Worktrees/rang/gemclean-memory2/.venv/Scripts/python.exe
fid=$1; tag=$2; run=$3; shift 3
case $fid in 0) t=J1331p3030;; 1) t=J1939m6342;; 2) t=J1833m2103;; esac
out=$P/runs/$t/$tag; rm -rf "$out"; mkdir -p "$out"
case "$run" in *python*) pre=("$run" -m rang.gemclean) ;; *) pre=("$run") ;; esac
s=$(date +%s)
"$PY" "$H/memtime.py" "$out/time.json" -- "${pre[@]}" -name "$out/image" -size 2048 2048 \
  -scale 2asec -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
  -data-column E2C_RANG_CORRECTED_DATA -field "$fid" -scans 17,18,19,20 -unit-weights \
  -no-update-model-required -j 4 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 \
  -wgridder-accuracy 0.0001 "$@" "$IN/f$fid.ms" > "$out/log.txt" 2>&1
rc=$?
(cd "$out" && sha256sum *.fits > fits.sha256; [ "${KEEP:-0}" = 1 ] || rm -f *.fits)
left=$(ls "$out" | grep -c '\.spill$\|\.tmp$' || true)
echo "$(date -Is) field $fid $tag rc=$rc secs=$(( $(date +%s) - s )) temp_left=$left" >> "$P/runs.log"
exit $rc
