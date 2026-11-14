#!/usr/bin/env bash
# prep.sh SKY... : gemclean_bench_compare.py prepare for each sky (Windows, Git Bash), each under
# the main checkout's heavy_lock (4 slots, 8 GB), into $O/prep/SKY. research/rml-gap.md.
set -u
W=$(cd "$(dirname "$0")/../../.." && pwd)
PY=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
O=D:/rang/outputs/rml-gap-20261113
B=D:/rang/outputs/20261102-gemclean/bench/data
H=D:/rang/outputs/20261103-gemclean-heldout/sim/data
for sky in "$@"; do
  case $sky in
    S1|S2|S3) l=$(echo "$sky" | tr S s); ms=$B/$l.ms; cat=$B/$l.json; noise="--noise $B/noise.c64"; n=2048 ;;
    H1|H2|H4) l=$(echo "$sky" | tr H h); ms=$H/$l.ms; cat=$H/$l.json; noise="--noise $H/$l.noise.c64"; n=2048 ;;
    H3) ms=$H/h3.ms; cat=$H/h3.json; noise="--noise $H/h3.noise.c64"; n=4096 ;;
    M1) ms=D:/rang/outputs/g5-20261107-03/data/m1.ms; cat=D:/rang/outputs/g5-20261107-03/data/m1.json; noise=""; n=2048 ;;
    N1|N2) l=$(echo "$sky" | tr N n); ms=$O/data/$l.ms; cat=$O/data/$l.json; noise="--noise $O/data/$l.noise.c64"; n=2048 ;;
  esac
  log=$O/logs/prep-$sky.log
  # Coordinator rule 2026-11-14: leave D: at least 150 GB free (prepare writes about 1.7 GB).
  free=$(df -BG --output=avail /d | tail -1 | tr -dc 0-9)
  if [ "$free" -lt 152 ]; then echo "D: has ${free} GB free: not preparing $sky" | tee "$log"; continue; fi
  echo "START $(date -Is) $sky" >"$log"
  t=$(date +%s)
  RAYON_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 $PY C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 4 --mem 8 -- \
    $PY "$W/examples/gemclean_bench_compare.py" prepare "$ms" "$cat" "$O/prep/$sky" --size $n --scale 1.5 $noise >>"$log" 2>&1
  echo "END $(date -Is) rc=$? wall=$(($(date +%s) - t))s" >>"$log"
done
