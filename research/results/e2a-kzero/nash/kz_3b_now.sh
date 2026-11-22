#!/bin/bash
# SPDX-License-Identifier: MIT
# research/e2a-kzero.md on nash: the calibrate-level readings. Waits until zs
# and zsd have finished calibrate; then, one branch per arm at once:
#   off:     the copy's hash, `rang-core run` (flag, calibrate; key off), keys,
#   every arm: the f0 flags export, the f0.ms copy, CASA's step-F arms tf, k;
# then kz_score.py score. Every step starts only inside the day window (after
# 06:00 SAST and, by its estimate, ending before 21:30), so the night budget
# stays with the two arm chains (4 + 4 slots). A step whose output exists is
# skipped, so a rerun after a failure is `bash kz_3b.sh` again (remove a failed
# CASA arm's directory O/ARM/f0/f0-casa-CASE first: k_run refuses an existing one).
#   bash kz_3b.sh
# kz_3b_now.sh (coordinator, 2026-11-17 20:00 SAST): owner lifted the time windows
# ("fill nash, make maximum usage"); same steps and bookings, no day window, and the
# off arm starts at once (it needs nothing from zs/zsd). Replaces the waiting kz_3b.sh.
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

calibrated() {  # ARM: calibrate done in its state.json
  "$PY" -c "import json,sys; s=json.load(open('$O/$1/e2a.ms.rang-run/state.json'))['stages']
sys.exit(0 if s.get('calibrate',{}).get('status')=='done' else 1)" 2>/dev/null
}

in_window() { return 0; }

step() {  # NAME SLOTS GB EST CMD...
  local name=$1 slots=$2 mem=$3 est=$4; shift 4
  while ! in_window "$est"; do sleep 300; done
  local t0; t0=$(date +%s)
  echo "$(date -Is) START $name slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots OPENBLAS_NUM_THREADS=$slots \
  MKL_NUM_THREADS=$slots NUMBA_NUM_THREADS=$slots K_THREADS=$slots \
    python3 "$LOCK" run --slots "$slots" --mem "$mem" -- nice -n 19 ionice -c3 "$@" \
    < /dev/null >> "$O/3b-$name.out" 2>&1
  local rc=$?
  local dt=$(( $(date +%s) - t0 ))
  echo "$(date -Is) END $name rc=$rc ${dt}s" >> "$LOG"
  printf '%s\t3b\t%s\t%s\t%s\t%s\n' "$(date -Is)" "$name" "$rc" "$dt" "$slots" >> "$O/timings.tsv"
  return $rc
}

off_run() {
  mkdir -p "$O/off/R"
  [ -f "$O/off/R/hash-copy.json" ] ||
    step off-hash 1 4 1800 "$PY" -c "import json, sys; sys.path.insert(0, '$S'); import e2_post as P
h = P.flag_hash('$O/off/e2a.ms'); w = json.load(open('$INPUT'))
ok = all(h[k] == w[k] for k in ('rows', 'flag_sha256', 'flag_row_sha256'))
json.dump({**h, 'input': w, 'met': ok}, open('$O/off/R/hash-copy.json', 'w'), indent=1)
sys.exit(0 if ok else 3)" || return 1
  "$PY" -c "import json,sys; sys.exit(0 if json.load(open('$O/off/R/hash-copy.json'))['met'] else 3)" || return 1
  # flag + calibrate: 7,128 s on the Windows host at 16 threads; at 8 here, estimate 4 h
  calibrated off ||
    step off-run 8 48 14400 "$PY" "$S/e2_timed.py" "$O/off/R/run-timed.json" -- \
      "$PY" -m rang.core_cli run "$K/e2a-kzero-off.yaml" "$O/off/e2a.ms" || return 1
  step off-keys 1 2 600 "$PY" "$K/kz_score.py" configs
}

arm() {  # ARM: flags, f0.ms, CASA tf then k
  local a=$1
  [ "$a" = off ] && { off_run || return 1; }
  [ -f "$O/$a/f0/f0win/flags.json" ] || step "flags-$a" 1 24 3600 "$PY" "$K/kz_f0.py" flags "$a" || return 1
  [ -d "$O/$a/f0/f0.ms" ] || step "prep-$a" 1 4 3600 "$PY" "$K/kz_f0.py" prep "$a" || return 1
  # step F: tf took 3,125 s and k 2,247 s with 4 threads (e2a-3b-k receipts)
  [ -d "$O/$a/f0/f0-casa-tf/B1" ] || step "casa-$a-tf" 4 16 7200 "$PY" "$K/kz_f0.py" casa "$a" tf || return 1
  [ -d "$O/$a/f0/f0-casa-k/B1" ] || step "casa-$a-k" 4 16 5400 "$PY" "$K/kz_f0.py" casa "$a" k || return 1
}

pids=()
arm off > "$O/3b-arm-off.log" 2>&1 &
pids+=($!)
echo "$(date -Is) off arm started now; waiting for zs and zsd calibrate" >> "$LOG"
until calibrated zs && calibrated zsd; do sleep 600; done
echo "$(date -Is) zs and zsd calibrate done" >> "$LOG"
for a in zs zsd; do
  arm "$a" > "$O/3b-arm-$a.log" 2>&1 &
  pids+=($!)
done
bad=0; for p in "${pids[@]}"; do wait "$p" || bad=1; done
[ $bad = 0 ] || { echo "$(date -Is) an arm of the 3b phase failed (O/3b-arm-*.log)" >> "$LOG"; exit 1; }
step score 2 64 3600 "$PY" "$K/kz_score.py" score || exit 1
echo "$(date -Is) 3B DONE" >> "$LOG"
