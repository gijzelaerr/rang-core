#!/bin/bash
# E2-N follow-up on nash (research/e2n-followup.md): one heavy-lock job per step
# (nice 19, ionice -c3), each inside e2_diskguard.py, on the follow-up's own MS copy.
#   bash fu_chain.sh FIRST [LAST]
# Environment: MS, R, INPUT (gate 2a's hashes), WPY (wheel venv python), FLOOR (GiB).
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
F=$W/research/results/e2n-followup/scripts
N=$W/research/results/e2n-scripts
S=$W/research/results/e2-acceptance-scripts
MS=${MS:-$HOME/rang-data/outputs/e2n-followup-20261118/e2n.ms}
R=${R:-$HOME/rang-data/outputs/e2n-followup-20261118/R}
INPUT=${INPUT:-$W/research/results/e2n/flaghash-input.json}
STRATEGY=$N/mk_rfi_flagging_calibrator_fields_firstpass.yaml
WPY=${WPY:-$W/.venv/bin/python}
LOCK=$HOME/Github/rang/tools/heavy_lock.py
FLOOR=${FLOOR:-1000}
KVERSION=${KVERSION:-rang_apply_20261117T034709Z}
MSDIR=$(dirname "$MS")
MSNAME=$(basename "$MS")
mkdir -p "$R"
LOG=$R/chain-steps.log
nash() { "$WPY" "$N/e2n_nash.py" "$@"; }
# step slots GB command...
STEPS="
tricolour 16 96 TRI run
tricolour-dump 1 16 TRI dump
tricolour-restore 1 4 TRI restore
casa-prep-a 1 8 FU prep-a
casa-run-a 4 32 FU run-a
k-only-m058 4 32 KONLY
casa-prep-b 1 8 FU prep-b
casa-run-b 4 32 FU run-b
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
final-restore 1 4 ROWSA final-restore $INPUT
"
first=${1:-tricolour}
last=${2:-final-restore}
on=0
while read -r step slots mem kind rest; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $kind in
    TRI) set -- $rest; sub=$1
         case $sub in run) cmd=("$WPY" "$F/fu_tricolour.py" run "$MS" "$R" "$STRATEGY") ;;
                      dump) cmd=("$WPY" "$F/fu_tricolour.py" dump "$MS" "$R") ;;
                      restore) cmd=("$WPY" "$F/fu_tricolour.py" restore "$MS" "$R" "$INPUT") ;; esac ;;
    FU) cmd=("$WPY" "$F/fu_casa3b.py" $rest "$MS" "$R") ;;
    KONLY) cmd=("$WPY" "$F/fu_casa3b.py" k-only "$MS" "$R" "$KVERSION" m058 m058) ;;
    CASA) cmd=(nash e2n_casa3b $rest "$MS" "$R") ;;
    SCORE3B) cmd=(nash e2n_score3b "$R" "$MS") ;;
    ROWSNAP_CASA) cmd=(nash e2n_rows snap casa "$MS" CORRECTED_DATA FLAG "$R/rows-casa.npy") ;;
    ROWSCORE) cmd=(nash e2n_rows score "$R/rows-rang.npy" "$R/rows-casa.npy" "$R/rows.json") ;;
    LEAK_CASA) cmd=(nash e2n_rows leakage "$MSDIR" "$MSNAME" CORRECTED_DATA "$R/leakage" casa) ;;
    ROWSA) set -- $rest; sub=$1; shift; cmd=(nash e2_rows_a "$sub" "$MS" "$R" "$@") ;;
  esac
  t0=$(date +%s)
  echo "$(date -Is) START $step slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 "$WPY" "$S/e2_diskguard.py" --path "$HOME" --min-free-gib "$FLOOR" --log "$R/chain-guard.jsonl" -- \
    bash -c "$(declare -f nash); WPY='$WPY' N='$N'; $(printf '%q ' "${cmd[@]}")" < /dev/null >> "$R/chain.out" 2>&1
  rc=$?
  echo "$(date -Is) END $step rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG"
  [ "$rc" = 0 ] || exit "$rc"
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
