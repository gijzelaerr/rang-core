#!/bin/bash
# E2-N's post chain (research/e2n-native.md section 6), E2-A's launcher with E2-N's
# paths: e2_post.py's
# ORDER_INPLACE, one shared heavy_lock job per step, each inside e2_diskguard.py
# (D: floor 165 GiB, 9.6). Git Bash. Start only after the rang arm has ended
# (its exclusive lock released) and its records are archived.
#   bash e2a_post.sh [FIRST_STEP] [LAST_STEP]
# Environment: MS, R (default D:\rang\outputs\e2a-20261115 and its e2a.ms),
# INPUT (gate 2a's hashes), STRATEGY (Tricolour's), PRIORITY (normal; critical
# only on the coordinator's word). NOSI=0 skips the optional nosi steps (9.10's
# decision: one -no-small-inversion dirty reading after the primary). DRY=1 prints each step's command and runs a
# stdin-reading stand-in in its place: no lock, nothing read or written.
# Each step's stdin is /dev/null: wsl.exe further down would otherwise drain
# the step list and end the loop early.
set -u
S=$(cd "$(dirname "$0")/../e2-acceptance-scripts" && pwd)
ROOT=$(cd "$S/../../.." && pwd)
export PYTHONUTF8=1
DRY=${DRY:-0}
NOSI=${NOSI:-1}
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
py='C:\Users\gijsm\Github\rang\.venv\Scripts\python.exe'  # main checkout's venv
wpy='C:\Users\gijsm\Build\tmp\20261116-e2n\wheel-venv\Scripts\python.exe'  # frozen wheel (6.4)
R=${R:-'D:\rang\outputs\e2n-20261116\R'}
MS=${MS:-'D:\rang\outputs\e2n-20261116\e2n.ms'}
angoutputse2n-20261116e2n.ms'}
INPUT=${INPUT:-$(cygpath -w "$ROOT/research/results/e2n/flaghash-input.json")}
STRATEGY=${STRATEGY:-$(cygpath -w "$S/mk_rfi_flagging_calibrator_fields_firstpass.yaml")}
PRIORITY=${PRIORITY:-normal}
post=$(cygpath -w "$S/e2_post.py")
guard=$(cygpath -w "$S/e2_diskguard.py")
if [ "$DRY" = 1 ]; then log=/dev/null; else log=$(cygpath -u "$R")/post-steps.log; fi
first=${1:-gate1}
last=${2:-tricolour}
runstep() {  # one step's whole command line
  if [ "$DRY" = 1 ]; then
    echo "DRY $*"
    cat > /dev/null  # drains its stdin, as wsl.exe may
  else
    "$@"
  fi
}
# step  slots  GB  python   (bookings: 9.10; wsclean -j and RAYON follow the slots)
STEPS="
gate1 1 2 py
archive 1 2 py
wcs 1 4 py
casacore 1 4 py
casa-ro 1 4 py
wsclean0 4 8 py
daskms 8 24 py
prep-inplace 1 4 py
applycal-inplace 2 8 py
compare-inplace 1 4 py
snapshot-inplace 1 12 py
drop-corrected-inplace 1 2 py
qc-avg 4 16 wpy
qc-selfcal 1 8 py
unit-on-a 1 2 py
wsclean3c-a-dirty 2 6 py
wsclean3c-a-clean 4 10 py
score3c-a 1 12 py
wsclean3c-a-nosi-dirty 2 6 py
score3c-a-nosi 1 8 py
unit-off-a 1 2 py
restore 1 4 py
tricolour 8 24 py
"
on=0
while read -r step slots mem which; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $step in *nosi*) [ "$NOSI" = 1 ] || { [ "$step" = "$last" ] && break; continue; } ;; esac
  case $step in
    restore) extra=("$INPUT") ;;
    tricolour) extra=("$INPUT" "$STRATEGY") ;;
    wsclean3c-a-dirty|wsclean3c-a-clean|wsclean3c-a-nosi-dirty) extra=("$slots") ;;
    *) extra=() ;;
  esac
  run=$py
  [ "$which" = wpy ] && run=$wpy
  t0=$(date +%s)
  RAYON_NUM_THREADS=$slots runstep "$py" "$lock" run --priority "$PRIORITY" --slots "$slots" \
    --mem "$mem" -- "$wpy" "$guard" --path 'D:/' --min-free-gib 165 --log "$R\\post-guard.jsonl" \
    -- "$run" "$post" "$step" "$MS" "$R" ${extra[@]+"${extra[@]}"} < /dev/null 2>&1 \
    | grep -v '^heavy_lock: waiting' | tee -a "$log"
  rc=${PIPESTATUS[0]}
  echo "$(date -Is) $step rc=$rc $(( $(date +%s) - t0 ))s slots=$slots mem=$mem" | tee -a "$log"
  [ "$rc" = 0 ] || exit "$rc"
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
