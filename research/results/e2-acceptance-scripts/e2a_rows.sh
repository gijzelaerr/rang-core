#!/bin/bash
# E2-A's oracle arms and rows after the in-place post chain (research/e2-acceptance.md
# 9.11): gate 3b's CASA arm and score, then the rows, one shared heavy_lock job per
# step, each inside e2_diskguard.py (D: floor 165 GiB). Git Bash. Run after
# e2a_post.sh has ended (restore and tricolour done).
#   bash e2a_rows.sh [FIRST_STEP] [LAST_STEP]
# Environment as e2a_post.sh (MS, R, INPUT, PRIORITY); FLUX_ARGS and FLUXS_ARGS
# override flux-prep's and flux-score's arguments (the development smoke only).
set -u
S=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$S/../../.." && pwd)
export PYTHONUTF8=1
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
py='C:\Users\gijsm\Github\rang\.venv\Scripts\python.exe'
wpy='C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv\Scripts\python.exe'
R=${R:-'D:\rang\outputs\e2a-20261115'}
MS=${MS:-"$R\\e2a.ms"}
INPUT=${INPUT:-$(cygpath -w "$ROOT/research/results/e2-acceptance/e2a-rerun/flaghash-input.json")}
PRIORITY=${PRIORITY:-normal}
FLUX_ARGS=${FLUX_ARGS:-}
FLUXS_ARGS=${FLUXS_ARGS:-}
rows=$(cygpath -w "$S/e2_rows_a.py")
casa=$(cygpath -w "$S/e2_casa3b_a.py")
s3b=$(cygpath -w "$S/e2_score3b_a.py")
guard=$(cygpath -w "$S/e2_diskguard.py")
log=$(cygpath -u "$R")/rows-steps.log
first=${1:-casa3b-prep}
last=${2:-final-restore}
# step  slots  GB
STEPS="
casa3b-prep 1 4
casa3b-run 4 16
score3b 1 8
selfcal-score 1 8
target-prep 1 8
target-applycal 2 12
target-unit-on 1 2
target-wsclean 4 10
target-unit-off 1 2
target-score 1 12
flux-prep 1 4
flux-run 4 16
flux-score 4 12
final-restore 1 4
"
on=0
while read -r step slots mem; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $step in
    casa3b-prep) cmd=("$py" "$casa" prep "$MS" "$R") ;;
    casa3b-run) cmd=("$py" "$casa" run "$MS" "$R") ;;
    score3b) cmd=("$py" "$s3b" "$R" "$MS") ;;
    flux-prep) cmd=("$py" "$rows" "$step" "$MS" "$R" $FLUX_ARGS) ;;
    flux-score) cmd=("$py" "$rows" "$step" "$MS" "$R" $FLUXS_ARGS) ;;
    target-wsclean) cmd=("$py" "$rows" "$step" "$MS" "$R" "$slots") ;;
    final-restore) cmd=("$py" "$rows" "$step" "$MS" "$R" "$INPUT") ;;
    *) cmd=("$py" "$rows" "$step" "$MS" "$R") ;;
  esac
  t0=$(date +%s)
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots "$py" "$lock" run --priority "$PRIORITY" \
    --slots "$slots" --mem "$mem" -- "$wpy" "$guard" --path 'D:/' --min-free-gib 165 \
    --log "$R\\rows-guard.jsonl" -- "${cmd[@]}" < /dev/null 2>&1 \
    | grep -v '^heavy_lock: waiting' >> "$log"
  rc=${PIPESTATUS[0]}
  echo "$(date -Is) $step rc=$rc $(( $(date +%s) - t0 ))s slots=$slots mem=$mem" | tee -a "$log"
  [ "$rc" = 0 ] || exit "$rc"
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
