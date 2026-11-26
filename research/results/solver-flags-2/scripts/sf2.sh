#!/bin/bash
# solver-flags-2 (#58), research/solver-flags-2.md section 7, on nash: shards with done-markers.
#   bash sf2.sh setup | move-r | prep ARM | run ARM | score
set -euo pipefail
WT=$HOME/Worktrees/rang/solver-flags-2
PY=$WT/.venv/bin/python
S=${SF2_S:-$WT/research/results/solver-flags-2/scripts}
# Inputs (prep) need no branch code: SF2_PREP_PY may name an older rang venv.
PREP_PY=${SF2_PREP_PY:-$PY}
DL0=${SF2_DL0:-$WT/research/results/dl0-profile/scripts/dl0_restore.py}
SRC=$HOME/rang-data/outputs/e2n-20261116
OLD=$HOME/rang-data/outputs/solver-flags-20261125
R=$HOME/rang-data/outputs/solver-flags-2-20261126
ONLINE=rang_flag_20261117T015729Z
RVER=rang_calibrate_20261125T180010Z   # R's flags after its flag stage (25 Nov), not the copied 17 Nov run
COPIED="J1331+3030 ASKAPJ1745 J0408-6545"
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
mkdir -p "$R/logs" "$R/cfg"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }
ARM=${2:-}
case ${1:-} in
setup)
  head=$(git -C "$WT" rev-parse --short HEAD)
  if ! shard "setup-$head"; then
    cd "$WT"
    [ -x .venv/bin/python ] || uv venv -q -p 3.12 .venv
    $NICE uv pip install -q -p .venv/bin/python --index-url https://pypi.org/simple maturin numpy scipy astropy pyyaml
    $LOCK --slots 8 --mem 16 -- $NICE env CARGO_BUILD_JOBS=8 bash -c \
      "cd $WT && VIRTUAL_ENV=$WT/.venv $WT/.venv/bin/maturin develop --release -q" > "$R/logs/build-$head.log" 2>&1
    "$PY" -c "import rang; print(rang.__file__)" >> "$R/logs/build-$head.log"
    mark "setup-$head"
  fi
  ;;
move-r)
  if ! shard move-r; then
    for x in e2n-R.ms e2n-R.ms.flagversions e2n-R.ms.rang-run; do mv "$OLD/$x" "$R/$x"; done
    mark move-r
  fi
  ;;
prep)
  ms=$R/e2n-$ARM.ms
  if ! shard "prep-$ARM"; then
    rm -rf "$ms" "$ms.flagversions" "$ms.rang-run"
    $LOCK --slots 1 --mem 4 -- $NICE bash -c "cp -a $SRC/e2n.ms $ms && cp -a $SRC/e2n.ms.flagversions $ms.flagversions"
    $LOCK --slots 1 --mem 8 -- $NICE "$PREP_PY" "$DL0" "$ms" "$ONLINE" "$R/restore-$ARM.json"
    $LOCK --slots 1 --mem 8 -- $NICE "$PREP_PY" -I "$S/sf2_rows.py" "$ms" "$R/e2n-R.ms" "$RVER" "$R/rows-$ARM.json" $COPIED > "$R/logs/rows-$ARM.log" 2>&1
    mark "prep-$ARM"
  fi
  if ! shard "cfg-$ARM"; then
    cp "${SF2_E2N:-$WT/research/results/e2n-scripts/e2n.yaml}" "$S/sf2_preset_only.yaml" "$R/cfg/"
    "$PREP_PY" -I "$S/sf2_cfg.py" "$R/cfg/e2n.yaml" "$R/cfg/e2n-$ARM.yaml" "$ARM"
    mark "cfg-$ARM"
  fi
  ;;
run)
  ms=$R/e2n-$ARM.ms
  if ! shard "run-$ARM"; then
    log "run-$ARM start $(git -C "$WT" rev-parse --short HEAD)"
    $LOCK --slots 3 --mem 32 -- $NICE env RAYON_NUM_THREADS=3 /usr/bin/time -v -o "$R/logs/run-$ARM.time" \
      "$PY" -m rang.core_cli run "$R/cfg/e2n-$ARM.yaml" "$ms" > "$R/logs/run-$ARM.log" 2>&1
    grep -q "apply: done" "$R/logs/run-$ARM.log" && mark "run-$ARM"
  fi
  ;;
score)
  $LOCK --slots 4 --mem 24 -- $NICE /usr/bin/time -v -o "$R/logs/score.time" \
    "$PY" -I "$S/sf2_score.py" e2n "$R" "$R/score.json" > "$R/logs/score.log" 2>&1
  ;;
*) echo "usage: sf2.sh setup|move-r|prep ARM|run ARM|score" >&2; exit 2;;
esac
