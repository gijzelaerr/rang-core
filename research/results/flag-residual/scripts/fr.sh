#!/bin/bash
# flag-residual (#51), research/flag-residual.md section 7: shards with done-markers on nash.
#   bash fr.sh setup | e2n | a1 | oracle | score
set -euo pipefail
WT=$HOME/Worktrees/rang/flag-residual
PY=$WT/.venv/bin/python
S=$WT/research/results/flag-residual/scripts
SRC=$HOME/rang-data/outputs/e2n-20261116
R=$HOME/rang-data/outputs/flag-residual-20261121
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs" "$R/cfg"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }

case ${1:-} in
setup)
  if ! shard setup; then
    cd "$WT"
    uv venv -q -p 3.12 .venv
    $NICE uv pip install -q -p .venv/bin/python --index-url https://pypi.org/simple maturin numpy scipy astropy pyyaml
    $LOCK --slots 8 --mem 16 -- $NICE env CARGO_BUILD_JOBS=8 bash -c \
      "cd $WT/core/py && VIRTUAL_ENV=$WT/.venv $WT/.venv/bin/maturin develop --release -q" > "$R/logs/build.log" 2>&1
    "$PY" -c "import rang, rang._core as c; assert hasattr(c, 'flag_residual_rang'); print(rang.__file__)" >> "$R/logs/build.log"
    mark setup
  fi
  ;;
e2n)
  for arm in off on; do
    if ! shard "copy-$arm"; then
      rm -rf "$R/e2n-$arm.ms" "$R/e2n-$arm.ms.flagversions"
      $LOCK --slots 1 --mem 2 -- $NICE bash -c "cp -a $SRC/e2n.ms $R/e2n-$arm.ms && cp -a $SRC/e2n.ms.flagversions $R/e2n-$arm.ms.flagversions"
      $NICE "$PY" "$WT/research/results/dl0-profile/scripts/dl0_restore.py" "$R/e2n-$arm.ms" \
        rang_calibrate_20261117T022650Z "$R/restore-$arm.json"
      mark "copy-$arm"
    fi
  done
  if ! shard cfg; then
    cp "$WT/research/results/e2n-scripts/e2n.yaml" "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$R/cfg/"
    "$PY" -I "$S/fr_cfg.py" "$R/cfg/e2n.yaml" "$R/cfg/e2n-off.yaml" off
    "$PY" -I "$S/fr_cfg.py" "$R/cfg/e2n.yaml" "$R/cfg/e2n-on.yaml" calibrators
    sha256sum "$R/cfg/"* > "$R/done.cfg"
  fi
  for arm in off on; do
    if ! shard "run-$arm"; then
      log "run-$arm start"
      $LOCK --slots 2 --mem 32 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o "$R/logs/run-$arm.time" \
        "$PY" -m rang.core_cli run "$R/cfg/e2n-$arm.yaml" "$R/e2n-$arm.ms" > "$R/logs/run-$arm.log" 2>&1 &
    fi
  done
  wait
  for arm in off on; do
    grep -q "apply: done" "$R/logs/run-$arm.log" && [ ! -e "$R/done.run-$arm" ] && mark "run-$arm"
  done
  ;;
a1)
  A=$R/a1
  mkdir -p "$A"
  if ! shard a1-gen; then
    $LOCK --slots 8 --mem 24 -- $NICE /usr/bin/time -v -o "$R/logs/a1-gen.time" \
      "$PY" -m rang.simtruth_ms generate full "$A/gen" --workers 8 > "$R/logs/a1-gen.log" 2>&1
    mark a1-gen
  fi
  if ! shard a1-cfg; then
    cp "$WT/research/results/e1-chain-scripts/e1_config.yaml" "$A/e1.yaml"
    cp "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$A/"
    "$PY" -I "$S/fr_cfg.py" "$A/e1.yaml" "$A/a1-off.yaml" off
    "$PY" -I "$S/fr_cfg.py" "$A/e1.yaml" "$A/a1-on.yaml" calibrators
    mark a1-cfg
  fi
  for arm in off on; do
    if ! shard "a1-copy-$arm"; then
      rm -rf "$A/a1-$arm.ms"; $NICE cp -a "$A/gen/a1-full.ms" "$A/a1-$arm.ms"; mark "a1-copy-$arm"
    fi
  done
  for arm in off on; do
    if ! shard "a1-run-$arm"; then
      log "a1-run-$arm start"
      $LOCK --slots 2 --mem 32 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o "$R/logs/a1-run-$arm.time" \
        "$PY" -m rang.core_cli run "$A/a1-$arm.yaml" "$A/a1-$arm.ms" > "$R/logs/a1-run-$arm.log" 2>&1 &
    fi
  done
  wait
  for arm in off on; do
    grep -q "apply: done" "$R/logs/a1-run-$arm.log" && [ ! -e "$R/done.a1-run-$arm" ] && mark "a1-run-$arm"
  done
  ;;
oracle)
  if ! shard oracle; then
    $LOCK --slots 2 --mem 24 -- $NICE "$PY" -I "$S/fr_oracle.py" dump "$R/e2n-on.ms" "$R/oracle" > "$R/logs/oracle-dump.log" 2>&1
    $LOCK --slots 2 --mem 24 -- $NICE apptainer exec --containall --env HOME=/tmp --bind "$R/oracle:/o" --bind "$S:/s" \
      "$HOME/rang-data/oracle-images/rang-formats-oracle_20261030.sif" sh -c "python -I /s/fr_oracle.py quartical /o" \
      > "$R/logs/oracle-qc.log" 2>&1
    $NICE "$PY" -I "$S/fr_oracle.py" compare "$R/oracle" > "$R/logs/oracle-compare.log" 2>&1
    mark oracle
  fi
  ;;
score)
  $NICE "$PY" -I "$S/fr_score.py" "$R" "$R/score.json" > "$R/logs/score.log" 2>&1
  ;;
*) echo "usage: fr.sh setup|e2n|a1|oracle|score" >&2; exit 2;;
esac
