#!/bin/bash
# DL0 (#37): one profiled run of E2-N's calibrate, apply and selfcal stages on
# nash (research/dl0-profile.md section 2). Shards with done-markers; a rerun
# skips finished shards, and `rang-core run` itself resumes per stage (the
# selfcal stage is one unit: its round directories are made fresh).
#
#   bash dl0_e2n_profile.sh            # run or resume every shard
#
# Inputs (read only): ~/rang-data/outputs/e2n-20261116/e2n.ms (+ .flagversions),
# its configuration research/results/e2n-scripts/e2n.yaml.
set -euo pipefail
WT=$HOME/Worktrees/rang/dl0-profile
PY=$WT/.venv/bin/python
SRC=$HOME/rang-data/outputs/e2n-20261116
R=$HOME/rang-data/outputs/dl0-profile-20261119
SCRIPTS=$WT/research/results/dl0-profile/scripts
mkdir -p "$R/cfg" "$R/logs"
log() { echo "$(date -Is) $*" | tee -a "$R/logs/driver.log"; }
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py"

# 1. Own copy of the MS (the source directory is never written).
if [ ! -e "$R/done.copy" ]; then
  log "copy start"
  rm -rf "$R/e2n.ms" "$R/e2n.ms.flagversions"
  $LOCK run --slots 1 --mem 2 -- nice -n 19 ionice -c3 \
    cp -a "$SRC/e2n.ms" "$SRC/e2n.ms.flagversions" "$R/"
  du -sb "$R/e2n.ms" > "$R/done.copy"
  log "copy done $(cat "$R/done.copy")"
fi

# 2. Flags as the flag stage left them: version rang_calibrate_* is saved
#    before calibrate's first flag write (docs/cli.md, `rang-core run`).
if [ ! -e "$R/done.restore" ]; then
  log "restore start"
  nice -n 19 ionice -c3 "$PY" "$SCRIPTS/dl0_restore.py" "$R/e2n.ms" \
    rang_calibrate_20261117T022650Z "$R/restore.json"
  touch "$R/done.restore"
  log "restore done"
fi

# 3. Configuration: E2-N's frozen file with run.stages without flag and image.
if [ ! -e "$R/done.cfg" ]; then
  cp "$WT/research/results/e2n-scripts/e2n.yaml" \
     "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$R/cfg/"
  sed -i 's/^  stages: \[flag, calibrate, apply, image, selfcal\]$/  stages: [calibrate, apply, selfcal]/' "$R/cfg/e2n.yaml"
  grep -q '^  stages: \[calibrate, apply, selfcal\]$' "$R/cfg/e2n.yaml"
  sha256sum "$R/cfg/"* > "$R/done.cfg"
fi

# 4. The run, sampled by py-spy at 1 Hz (Python stacks with native frames, all
#    threads, subprocesses). One attempt file per start, so a resumed stage
#    keeps the earlier samples.
if [ ! -e "$R/done.run" ]; then
  n=$(find "$R/logs" -name 'run-attempt-*.log' | wc -l)
  a=$((n + 1))
  log "run attempt $a start"
  $LOCK run --slots 16 --mem 64 -- nice -n 19 ionice -c3 \
    env RAYON_NUM_THREADS=16 OMP_NUM_THREADS=16 \
    /usr/bin/time -v -o "$R/logs/run-attempt-$a.time" \
    "$WT/.venv/bin/py-spy" record --rate 1 --idle --subprocesses --threads \
      --format raw -o "$R/pyspy-attempt-$a.txt" -- \
    "$PY" -m rang.core_cli run "$R/cfg/e2n.yaml" "$R/e2n.ms" \
    > "$R/logs/run-attempt-$a.log" 2>&1
  touch "$R/done.run"
  log "run attempt $a done"
fi
log "all shards done"
