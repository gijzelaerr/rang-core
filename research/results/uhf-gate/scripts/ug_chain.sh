#!/bin/bash
# SPDX-License-Identifier: MIT
# The UHF gate on nash (research/uhf-gate.md sections 4-8): the rang arm and the
# post chain of one block, E2-N's chain (e2n_nash_chain.sh, fu_chain.sh) with the
# protocol's UHF steps (ug.py). Self-driving: each step leaves $R/done/<step>, so a
# second start resumes; `run` is never started twice (a started, unfinished run
# stops the chain for a decision). One heavy-lock booking per step (the main
# checkout's tools/heavy_lock.py), every step nice 19 / ionice idle inside
# e2_diskguard.py (floor $FLOOR GiB on /home).
#   UG_BLOCK=D|H|A1 MS=... CONFIG=... CONFIG3C=... INPUT=... \
#     nohup bash ug_chain.sh [FIRST [LAST]] >> $R/ug-chain.out 2>&1 &
# Environment: UG_BLOCK, MS, R (result directory), CONFIG, CONFIG3C (in the
# block's cfg/ with firstpass_UHF.yaml beside them), INPUT (gate 2a's hashes),
# WPY (frozen wheel venv), PY (scripts venv), FLOOR, ST (status file line).
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
U=$W/research/results/uhf-gate/scripts
N=$W/research/results/e2n-scripts
S=$W/research/results/e2-acceptance-scripts
LOCK=$HOME/Github/rang/tools/heavy_lock.py
B=$HOME/Build/tmp/20261126-uhf-gate
WPY=${WPY:-$B/wheel-venv/bin/python}
PY=${PY:-$W/.venv/bin/python}
FLOOR=${FLOOR:-2000}
# the run and casa-model steps hold the model predict, threaded by rayon in the
# pipeline process (predict-par, amendment 3): RAYON_NUM_THREADS = these slots
RUN_SLOTS=${RUN_SLOTS:-16}
# scripts that put the worktree's python/ first (e1_run.py) need the frozen wheel's
# extension there: the worktree's python/ is the wheel's source, so link its _core
if ! ls "$W"/python/rang/_core*.so > /dev/null 2>&1; then
  ln -s "$("$WPY" -c 'import os, rang; print(os.path.dirname(rang.__file__))')/_core.abi3.so" \
    "$W/python/rang/_core.abi3.so"
fi
STRATEGY=$(dirname "$CONFIG")/firstpass_UHF.yaml
STRATEGY_SHA=4c336933bd6c4ad2c075945394d76e270665ce301b8353b7974601e3a0459856
export UG_BLOCK UG_0407_CAT=$HOME/rang-data/uhf/reference/ez63-vx81/fitted.PKS0407.UBand.wsclean.cat.txt
MSDIR=$(dirname "$MS")
mkdir -p "$R/done"
LOG=$R/chain-steps.log
note() { echo "$(date -Is) $UG_BLOCK $*" | tee -a "$R/ug-chain.log"; }
did() { [ -e "$R/done/$1" ]; }
source "$HOME/.rang-env.sh" >/dev/null 2>&1
[ "$(sha256sum < "$STRATEGY" | cut -c1-64)" = "$STRATEGY_SHA" ] || { note "strategy hash differs"; exit 2; }
LEAK=1; [ "$UG_BLOCK" = D ] && LEAK=0
# e2n-scripts read their fields from E2N_* (ug.py sets them for itself)
case $UG_BLOCK in
  D) export E2N_FCAL=J1939-6342 E2N_XCAL=J1331+3030 E2N_GCAL=J1609+2641 E2N_TARGET=ILTJ153010 E2N_LEAK= ;;
  H) export E2N_FCAL=J1939-6342 E2N_XCAL=J1331+3030 E2N_GCAL=J1605-1734 E2N_TARGET=HD142184 E2N_LEAK=J0408-6545 ;;
  A1) export E2N_FCAL=J1939-6342 E2N_XCAL=3C286-SIM E2N_GCAL=SIM-GCAL E2N_TARGET=SIM-TARGET E2N_LEAK=SIM-GCAL ;;
  *) note "UG_BLOCK $UG_BLOCK"; exit 2 ;;
esac

# step slots GB kind args...  (bookings: E2-N's scaled by the cells, D 2.6x, H 3.7x)
STEPS="
config-check 1 8 CFGCHECK
columns-before 1 2 POST
run $RUN_SLOTS 128 RUN
gate1 1 2 POST
archive 1 4 POST
wcs 1 8 POST
casacore 1 8 POST
casa-ro 1 8 POST
wsclean0 4 48 POST
daskms 8 64 POST
model-row 16 48 UG model-row $HOME/rang-data/uhf/reference/hhhy-4r55/fitted.PKS1934.UBand.wsclean.cat.txt
c3-flag 1 8 UG c3-flag
c3-run 16 160 C3RUN
c3-unit-on 1 4 UG c3-unit on
ws3c-dirty 8 64 UG ws3c dirty 8
ws3c-clean 16 96 UG ws3c clean 16
c3-unit-off 1 4 UG c3-unit off
score3c 1 48 UG score3c
prep-inplace 1 8 POST
applycal-inplace 4 48 POST
compare-inplace 1 16 POST
snapshot-inplace 1 24 POST
rows-snap-rang 1 16 UG rows-snap rang RANG_CORRECTED_DATA RANG_FLAG RANG_MODEL_DATA $R/rows-rang.npy
drop-corrected-inplace 1 2 POST
qc-avg 4 96 POSTW
qc-selfcal 4 128 POST
unit-on-a 1 4 POST
leakage-rang 8 48 UG leakage RANG_CORRECTED_DATA rang
unit-off-a 1 4 POST
restore 1 8 RESTORE
tricolour 16 192 TRICOLOUR
casa-model $RUN_SLOTS 48 UG casa-model $CONFIG
casa-prep-a 1 8 UG casa-prep-a
casa-run-a 4 64 UG casa-run-a
casa-prep-b 1 8 UG casa-prep-b
casa-run-b 4 64 UG casa-run-b
score3b 1 32 SCORE3B
casa-corr-prep 1 8 UG casa-corr-prep
casa-applycal 4 64 UG casa-applycal
rows-snap-casa 1 16 UG rows-snap casa CORRECTED_DATA FLAG MODEL_DATA $R/rows-casa.npy
rows-score 1 4 UG rows-score
target-unit-on 1 4 ROWSA target-unit-on
leakage-casa 8 48 UG leakage CORRECTED_DATA casa
leak-score 1 2 UG leak-score
target-wsclean 16 96 UG target-wsclean 16
target-unit-off 1 4 ROWSA target-unit-off
target-score 1 48 UG target-score
selfcal-score 1 32 UG selfcal-score
native-size 1 8 NATIVE
reported 1 2 UG reported
final-restore 1 8 ROWSA final-restore $INPUT
"
first=${1:-config-check}
last=${2:-final-restore}
on=0
while read -r step slots mem kind rest; do
  [ -n "$step" ] || continue
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  if did "$step"; then [ "$step" = "$last" ] && break; continue; fi
  case $step in *leak*) [ $LEAK = 1 ] || { [ "$step" = "$last" ] && break; continue; } ;; esac
  case $kind in
    CFGCHECK) cmd=(bash -c "'$WPY' -m rang.core_cli config check '$CONFIG' '$MS' > '$R/config-check.txt' 2>&1 && '$WPY' -m rang.core_cli config check '$CONFIG3C' '$MS' >> '$R/config-check.txt' 2>&1") ;;
    RUN) if [ -e "$R/run.started" ]; then note "run was started before and is not done: not restarted (a decision)"; exit 4; fi
         touch "$R/run.started"
         cmd=("$WPY" "$S/e2_timed.py" "$R/run-timed.json" -- "$WPY" -m rang.core_cli run "$CONFIG" "$MS") ;;
    C3RUN) if [ -e "$R/c3-run.started" ]; then note "c3-run was started before and is not done"; exit 4; fi
           touch "$R/c3-run.started"
           cmd=("$WPY" "$S/e2_timed.py" "$R/c3-run-timed.json" -- "$WPY" -m rang.core_cli run "$CONFIG3C" "$MS" --run-dir "$R/c3/rang-run") ;;
    POST) cmd=("$PY" "$N/e2n_nash.py" e2_post "$step" "$MS" "$R") ;;
    POSTW) cmd=("$WPY" "$N/e2n_nash.py" e2_post "$step" "$MS" "$R") ;;
    POSTJ) cmd=("$PY" "$N/e2n_nash.py" e2_post "$step" "$MS" "$R" "$slots") ;;
    RESTORE) cmd=("$PY" "$N/e2n_nash.py" e2_post restore "$MS" "$R" "$INPUT") ;;
    TRICOLOUR) cmd=("$PY" "$N/e2n_nash.py" e2_post tricolour "$MS" "$R" "$INPUT" "$STRATEGY") ;;
    UG) set -- $rest; sub=$1; shift; cmd=("$PY" "$U/ug.py" "$sub" "$MS" "$R" "$@") ;;
    SCORE3B) cmd=("$PY" "$N/e2n_nash.py" e2n_score3b "$R" "$MS") ;;
    ROWSA) set -- $rest; sub=$1; shift; cmd=("$PY" "$N/e2n_nash.py" e2_rows_a "$sub" "$MS" "$R" "$@") ;;
    NATIVE) cmd=("$PY" "$N/e2n_native_size.py" "$R/rang-run-moved/calibrate" "$R/casa/tables" "$R/native-size.json") ;;
  esac
  t0=$(date +%s)
  echo "$(date -Is) START $step slots=$slots mem=$mem" >> "$LOG"
  RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 /usr/bin/time -v -o "$R/time-$step.txt" \
    "$WPY" "$S/e2_diskguard.py" --path "$HOME" --min-free-gib "$FLOOR" --log "$R/chain-guard.jsonl" -- \
    "${cmd[@]}" < /dev/null >> "$R/chain.out" 2>&1
  rc=$?
  echo "$(date -Is) END $step rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG"
  [ "$rc" = 0 ] || { note "stopped at $step rc=$rc"; exit "$rc"; }
  touch "$R/done/$step"
  note "done $step $(( $(date +%s) - t0 ))s"
  [ "$step" = "$last" ] && break
done <<< "$STEPS"
note "chain $first..$last finished"
