#!/bin/bash
# SPDX-License-Identifier: MIT
# research/e2a-kzero.md on nash: the calibrate-level readings. Arm OFF (flag and
# calibrate, key off), then for zs, zsd and off: the f0 flags export, the f0.ms
# copy, CASA's step-F arms tf and k, and kz_score.py. Waits until zs and zsd
# have finished calibrate. Every step runs only inside the day window
# (starts after 06:00 SAST and, by its estimate, ends before 21:30), so the
# night budget stays with the two arm chains (4 + 4 slots).
#   bash kz_3b.sh [FIRST]
# Log: O/3b-steps.log ("3B DONE" at the end).
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
K=$W/research/results/e2a-kzero
S=$W/research/results/e2-acceptance-scripts
O=$HOME/rang-data/outputs/e2a-kzero-20261117
PY=$W/.venv/bin/python
LOCK=$HOME/Github/rang/tools/heavy_lock.py
LOG=$O/3b-steps.log
INPUT=$W/research/results/e2-acceptance/e2a-rerun/flaghash-input.json
first=${1:-wait-calibrate}

calibrated() {  # ARM: calibrate done in its state.json
  "$PY" -c "import json,sys; s=json.load(open('$O/$1/e2a.ms.rang-run/state.json'))['stages']
sys.exit(0 if s.get('calibrate',{}).get('status')=='done' else 1)" 2>/dev/null
}

in_window() {  # EST seconds: now >= 06:00 and now + EST <= 21:30 (SAST)
  local now s0 s1
  now=$(TZ=Africa/Johannesburg date +%s)
  s0=$(TZ=Africa/Johannesburg date -d "today 06:00" +%s)
  s1=$(TZ=Africa/Johannesburg date -d "today 21:30" +%s)
  [ "$now" -ge "$s0" ] && [ $(( now + $1 )) -le "$s1" ]
}

step() {  # NAME SLOTS GB EST CMD...
  local name=$1 slots=$2 mem=$3 est=$4; shift 4
  while ! in_window "$est"; do sleep 300; done
  local t0; t0=$(date +%s)
  echo "$(date -Is) START $name slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots OPENBLAS_NUM_THREADS=$slots \
  MKL_NUM_THREADS=$slots NUMBA_NUM_THREADS=$slots K_THREADS=$slots \
    python3 "$LOCK" run --slots "$slots" --mem "$mem" -- nice -n 19 ionice -c3 "$@" \
    < /dev/null >> "$O/3b.out" 2>&1
  local rc=$?
  local dt=$(( $(date +%s) - t0 ))
  echo "$(date -Is) END $name rc=$rc ${dt}s" >> "$LOG"
  printf '%s\t3b\t%s\t%s\t%s\t%s\n' "$(date -Is)" "$name" "$rc" "$dt" "$slots" >> "$O/timings.tsv"
  return $rc
}

on=0
run_from() { [ "$1" = "$first" ] && on=1; [ $on = 1 ]; }

if run_from wait-calibrate; then
  echo "$(date -Is) waiting for zs and zsd calibrate" >> "$LOG"
  until calibrated zs && calibrated zsd; do sleep 600; done
  echo "$(date -Is) zs and zsd calibrate done" >> "$LOG"
fi
if run_from off-hash; then
  mkdir -p "$O/off/R"
  step off-hash 1 4 1800 "$PY" -c "import json, sys; sys.path.insert(0, '$S'); import e2_post as P
h = P.flag_hash('$O/off/e2a.ms'); w = json.load(open('$INPUT'))
ok = all(h[k] == w[k] for k in ('rows', 'flag_sha256', 'flag_row_sha256'))
json.dump({**h, 'input': w, 'met': ok}, open('$O/off/R/hash-copy.json', 'w'), indent=1)
sys.exit(0 if ok else 3)" || exit 1
fi
if run_from off-run; then
  # flag + calibrate on the Windows host: 7,128 s at 16 threads; nash at 8: estimate 4 h
  step off-run 8 48 14400 "$PY" "$S/e2_timed.py" "$O/off/R/run-timed.json" -- \
    "$PY" -m rang.core_cli run "$K/e2a-kzero-off.yaml" "$O/off/e2a.ms" || exit 1
  step off-keys 1 2 600 "$PY" "$K/kz_score.py" configs || exit 1
fi
if run_from flags; then
  for a in zs zsd off; do
    step "flags-$a" 1 24 3600 "$PY" "$K/kz_f0.py" flags "$a" || exit 1
    [ -d "$O/$a/f0/f0.ms" ] || { step "prep-$a" 1 4 3600 "$PY" "$K/kz_f0.py" prep "$a" || exit 1; }
  done
fi
if run_from casa; then
  # step F's tf took 3,125 s and k 2,247 s at 4 threads (e2a-3b-k receipts); three arms at once
  pids=()
  for a in zs zsd off; do
    ( step "casa-$a-tf" 4 16 7200 "$PY" "$K/kz_f0.py" casa "$a" tf &&
      step "casa-$a-k" 4 16 5400 "$PY" "$K/kz_f0.py" casa "$a" k ) &
    pids+=($!)
  done
  bad=0; for p in "${pids[@]}"; do wait "$p" || bad=1; done
  [ $bad = 0 ] || { echo "$(date -Is) a CASA arm failed" >> "$LOG"; exit 1; }
fi
if run_from score; then
  step score 2 64 3600 "$PY" "$K/kz_score.py" score || exit 1
fi
echo "$(date -Is) 3B DONE" >> "$LOG"
