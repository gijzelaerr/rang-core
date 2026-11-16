#!/bin/bash
# E2-N on nash (research/e2n-native.md amendment 3): the rang arm and the post
# chain, one heavy-lock job per step (the lock adds nice -n 19 ionice -c3 on
# nash, RANG_HEAVY_NICE=19), each inside e2_diskguard.py, oracle containers by
# apptainer through e2n_nash.py.
#   bash e2n_nash_chain.sh FIRST [LAST]     steps in the order of STEPS below
# Environment: MS (the leg's MS), R (its result directory), CONFIG (for `run`),
# INPUT (gate 2a's hashes), WPY (wheel venv python), PY (worktree venv python),
# NOSI (1: the optional -no-small-inversion reading), FLOOR (GiB, default 1000).
set -u
W=$(cd "$(dirname "$0")/../../.." && pwd)
N=$W/research/results/e2n-scripts
S=$W/research/results/e2-acceptance-scripts
MS=${MS:-$HOME/rang-data/outputs/e2n-20261116/e2n.ms}
R=${R:-$HOME/rang-data/outputs/e2n-20261116/R}
CONFIG=${CONFIG:-$N/e2n.yaml}
INPUT=${INPUT:-$W/research/results/e2n/flaghash-input.json}
STRATEGY=$N/mk_rfi_flagging_calibrator_fields_firstpass.yaml
WPY=${WPY:-$HOME/Build/tmp/20261116-e2n/wheel-venv/bin/python}
PY=${PY:-$W/.venv/bin/python}
LOCK=$HOME/Github/rang/tools/heavy_lock.py
NOSI=${NOSI:-1}
FLOOR=${FLOOR:-1000}
MSDIR=$(dirname "$MS")
MSNAME=$(basename "$MS")
mkdir -p "$R"
LOG=$R/chain-steps.log
nash() { "$PY" "$N/e2n_nash.py" "$@"; }
# step slots GB command...
STEPS="
columns-before 1 2 POST
run 16 96 RUN
gate1 1 2 POST
archive 1 2 POST
wcs 1 4 POST
casacore 1 4 POST
casa-ro 1 4 POST
wsclean0 4 16 POST
daskms 8 32 POST
prep-inplace 1 8 POST
applycal-inplace 4 16 POST
compare-inplace 1 8 POST
snapshot-inplace 1 12 POST
rows-snap-rang 1 8 ROWSNAP_RANG
drop-corrected-inplace 1 2 POST
qc-avg 4 32 POSTW
qc-selfcal 4 64 POST
unit-on-a 1 2 POST
leakage-rang 8 32 LEAK_RANG
wsclean3c-a-dirty 4 32 POSTJ
wsclean3c-a-clean 8 64 POSTJ
score3c-a 1 16 POST
wsclean3c-a-nosi-dirty 4 32 POSTJ
score3c-a-nosi 1 16 POST
unit-off-a 1 2 POST
restore 1 4 RESTORE
tricolour 16 96 TRICOLOUR
casa3b-prep 1 8 CASA prep
casa3b-run 4 32 CASA run
score3b 1 16 SCORE3B
casa-corr-prep 1 8 CASA corr-prep
casa-applycal 4 32 CASA applycal
rows-snap-casa 1 8 ROWSNAP_CASA
rows-score 1 4 ROWSCORE
target-unit-on 1 2 ROWSA target-unit-on
leakage-casa 8 32 LEAK_CASA
target-wsclean 8 64 ROWSA target-wsclean 8
target-unit-off 1 2 ROWSA target-unit-off
target-score 1 16 ROWSA target-score
selfcal-score 1 16 ROWSA selfcal-score
final-restore 1 4 ROWSA final-restore $INPUT
"
first=${1:-columns-before}
last=${2:-final-restore}
on=0
while read -r step slots mem kind rest; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $step in *nosi*) [ "$NOSI" = 1 ] || { [ "$step" = "$last" ] && break; continue; } ;; esac
  case $kind in
    RUN) cmd=("$WPY" "$S/e2_timed.py" "$R/../$(basename "$R")-run-timed.json" -- "$WPY" -m rang.core_cli run "$CONFIG" "$MS") ;;
    POST) cmd=(nash e2_post "$step" "$MS" "$R") ;;
    POSTW) cmd=("$WPY" "$N/e2n_nash.py" e2_post "$step" "$MS" "$R") ;;
    POSTJ) cmd=(nash e2_post "$step" "$MS" "$R" "$slots") ;;
    RESTORE) cmd=(nash e2_post restore "$MS" "$R" "$INPUT") ;;
    TRICOLOUR) cmd=(nash e2_post tricolour "$MS" "$R" "$INPUT" "$STRATEGY") ;;
    ROWSNAP_RANG) cmd=(nash e2n_rows snap rang "$MS" RANG_CORRECTED_DATA RANG_FLAG "$R/rows-rang.npy") ;;
    ROWSNAP_CASA) cmd=(nash e2n_rows snap casa "$MS" CORRECTED_DATA FLAG "$R/rows-casa.npy") ;;
    ROWSCORE) cmd=(nash e2n_rows score "$R/rows-rang.npy" "$R/rows-casa.npy" "$R/rows.json") ;;
    LEAK_RANG) cmd=(nash e2n_rows leakage "$MSDIR" "$MSNAME" RANG_CORRECTED_DATA "$R/leakage" rang) ;;
    LEAK_CASA) cmd=(nash e2n_rows leakage "$MSDIR" "$MSNAME" CORRECTED_DATA "$R/leakage" casa) ;;
    CASA) cmd=(nash e2n_casa3b $rest "$MS" "$R") ;;
    SCORE3B) cmd=(nash e2n_score3b "$R" "$MS") ;;
    ROWSA) set -- $rest; sub=$1; shift; cmd=(nash e2_rows_a "$sub" "$MS" "$R" "$@") ;;
  esac
  t0=$(date +%s)
  echo "$(date -Is) START $step slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    "$WPY" "$S/e2_diskguard.py" --path "$HOME" --min-free-gib "$FLOOR" --log "$R/chain-guard.jsonl" -- \
    bash -c "$(declare -f nash); PY='$PY' N='$N'; $(printf '%q ' "${cmd[@]}")" < /dev/null >> "$R/chain.out" 2>&1
  rc=$?
  echo "$(date -Is) END $step rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG"
  [ "$rc" = 0 ] || exit "$rc"
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
