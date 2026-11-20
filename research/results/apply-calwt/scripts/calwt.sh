#!/bin/bash
# apply-calwt (#48), research/apply-calwt.md: E2-N shards with done-markers on nash.
#   bash calwt.sh        # run or resume every shard in order
set -euo pipefail
WT=$HOME/Worktrees/rang/apply-calwt
PY=$WT/.venv/bin/python
S=$WT/research/results/apply-calwt/scripts
SRC=$HOME/rang-data/outputs/e2n-20261116
R=$HOME/rang-data/outputs/apply-calwt-20261120
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs" "$R/cfg" "$R/score"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }

if ! shard copy; then
  log "copy start"; rm -rf "$R/e2n.ms" "$R/e2n.ms.flagversions"
  $LOCK --slots 1 --mem 2 -- $NICE cp -a "$SRC/e2n.ms" "$SRC/e2n.ms.flagversions" "$R/"
  mark copy
fi
if ! shard restore; then
  $NICE "$PY" "$WT/research/results/dl0-profile/scripts/dl0_restore.py" "$R/e2n.ms" \
    rang_calibrate_20261117T022650Z "$R/restore.json"
  mark restore
fi
if ! shard cfg; then
  cp "$WT/research/results/e2n-scripts/e2n.yaml" \
     "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$R/cfg/"
  sed -i 's/^  stages: \[flag, calibrate, apply, image, selfcal\]$/  stages: [calibrate, apply]/' "$R/cfg/e2n.yaml"
  grep -q '^  stages: \[calibrate, apply\]$' "$R/cfg/e2n.yaml"
  grep -q '^  calwt: false$' "$R/cfg/e2n.yaml"
  sed 's/^  calwt: false$/  calwt: true/' "$R/cfg/e2n.yaml" > "$R/cfg/e2n-calwt.yaml"
  grep -q '^  calwt: true$' "$R/cfg/e2n-calwt.yaml"
  sha256sum "$R/cfg/"* > "$R/done.cfg"
fi
# Arm F: calibrate and apply as frozen (calwt false); one core each phase.
if ! shard runF; then
  log "runF start"
  $LOCK --slots 2 --mem 16 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o "$R/logs/runF.time" \
    "$PY" -m rang.core_cli run "$R/cfg/e2n.yaml" "$R/e2n.ms" > "$R/logs/runF.log" 2>&1
  cp -r "$R/e2n.ms.rang-run/apply" "$R/apply-F"
  mark runF
fi
# Scores of the raw weights (F) and of unity weights (U), from the same pass.
if ! shard scoreF; then
  log "scoreF start"
  $LOCK --slots 2 --mem 24 -- $NICE /usr/bin/time -v -o "$R/logs/scoreF.time" \
    "$PY" -I "$S/calwt_score.py" "$R/e2n.ms" F "$R/score/F.json" > "$R/logs/scoreF.log" 2>&1
  mark scoreF
fi
# Arm T: apply again with calwt true on the same tables.
if ! shard applyT; then
  log "applyT start"
  $LOCK --slots 2 --mem 16 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o "$R/logs/applyT.time" \
    "$PY" -m rang.core_cli run --force apply "$R/cfg/e2n-calwt.yaml" "$R/e2n.ms" > "$R/logs/applyT.log" 2>&1
  mark applyT
fi
if ! shard scoreT; then
  log "scoreT start"
  $LOCK --slots 2 --mem 24 -- $NICE /usr/bin/time -v -o "$R/logs/scoreT.time" \
    "$PY" -I "$S/calwt_score.py" "$R/e2n.ms" T "$R/score/T.json" --save-weights "$R/score/T-weights.npz" \
    > "$R/logs/scoreT.log" 2>&1
  mark scoreT
fi
# Oracle: CASA applycal (calwt as rang's apply summary records it) on the same MS, then compare.
if ! shard oracle; then
  log "oracle start"
  # the container sees only the MS's directory (/c) and R/oracle (/p): copy the tables in
  rm -rf "$R/oracle"; mkdir -p "$R/oracle/rang-run"
  cp -r "$R/e2n.ms.rang-run/calibrate" "$R/e2n.ms.rang-run/apply" "$R/oracle/rang-run/"
  $LOCK --slots 4 --mem 32 -- "$PY" -I "$S/calwt_oracle.py" "$R/e2n.ms" "$R/oracle" > "$R/logs/oracle.log" 2>&1
  mark oracle
fi
if ! shard compare; then
  $LOCK --slots 2 --mem 16 -- $NICE "$PY" -I "$S/calwt_score.py" "$R/e2n.ms" O "$R/score/O.json" \
    --compare-weights "$R/score/T-weights.npz" > "$R/logs/compare.log" 2>&1
  mark compare
fi
log "all done"
