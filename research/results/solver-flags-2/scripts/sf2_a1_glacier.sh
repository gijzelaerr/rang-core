#!/bin/bash
# solver-flags-2 (#58): A1's arms P0, PB, PG, PBG on glacier (Git Bash), research/solver-flags-2.md
# section 4. Shards with done-markers under D:/rang/outputs/solver-flags-2-20261126.
#   bash sf2_a1_glacier.sh move | arm ARM | score | all
set -euo pipefail
WT=/c/Users/gijsm/Worktrees/rang/solver-flags-2
PY=$WT/.venv/Scripts/python.exe
S=$WT/research/results/solver-flags-2/scripts
PREP_PY=${SF2_PREP_PY:-$PY}  # inputs need no branch code
OLD=/d/rang/outputs/solver-flags-20261125
R=/d/rang/outputs/solver-flags-2-20261126
A=$R/a1
RVER=rang_calibrate_20261125T100613Z   # A1 R's flags after its flag stage
LOCK="python /c/Users/gijsm/Github/rang/tools/heavy_lock.py run"
mkdir -p "$R/logs" "$A"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }
timed() { local name=$1; shift; local t0=$(date +%s) rc=0; "$@" || rc=$?; echo "$name $(( $(date +%s) - t0 )) s rc=$rc" >> "$R/logs/times.txt"; return $rc; }
move() {
  if ! shard move; then
    for x in gen a1-R.ms a1-R.ms.flagversions a1-R.ms.rang-run a1-R.yaml; do mv "$OLD/a1/$x" "$A/$x"; done
    mark move
  fi
}
arm() {
  local ARM=$1 ms=$A/a1-$1.ms
  if ! shard "a1-prep-$ARM"; then
    rm -rf "$ms" "$ms.flagversions" "$ms.rang-run"
    timed "a1-copy-$ARM" cp -r "$A/gen/a1-full.ms" "$ms"
    timed "a1-rows-$ARM" $LOCK --slots 1 --mem 4 -- "$PREP_PY" -I "$S/sf2_rows.py" "$ms" "$A/a1-R.ms" "$RVER" "$A/rows-$ARM.json" 3C286-SIM SIM-TARGET > "$R/logs/a1-rows-$ARM.log" 2>&1
    mark "a1-prep-$ARM"
  fi
  if ! shard "a1-cfg-$ARM"; then
    cp "$WT/research/results/e1-chain-scripts/e1_config.yaml" "$A/e1.yaml"
    cp "$S/sf2_preset_only.yaml" "$A/"
    # memory 12 GiB inside a 16 GB booking, as the first note's A1 arms.
    "$PREP_PY" -I "$S/sf2_cfg.py" "$A/e1.yaml" "$A/a1-$ARM.yaml" "$ARM" 12
    mark "a1-cfg-$ARM"
  fi
  [ -n "${ARMS_PREP_ONLY:-}" ] && return 0
  if ! shard "a1-run-$ARM"; then
    log "a1-run-$ARM start $(git -C "$WT" rev-parse --short HEAD)"
    timed "a1-run-$ARM" $LOCK --slots 4 --mem 16 -- env RAYON_NUM_THREADS=4 "$PY" -m rang.core_cli run "$A/a1-$ARM.yaml" "$ms" > "$R/logs/a1-run-$ARM.log" 2>&1
    grep -q "apply: done" "$R/logs/a1-run-$ARM.log" && mark "a1-run-$ARM"
  fi
}
score() { timed a1-score "$PY" -I "$S/sf2_score.py" a1 "$R" "$R/a1-records.json" > "$R/logs/a1-score.log" 2>&1; }
case ${1:-} in
move) move ;;
arm) arm "$2" ;;
prep) ARMS_PREP_ONLY=1 arm "$2" ;;
score) score ;;
all) move; for a in P0 PB PG PBG; do arm $a || echo "$(date -Is) FAILED a1-$a" >> "$R/logs/FAILED"; done; score ;;
*) echo "usage: sf2_a1_glacier.sh move|arm ARM|score|all" >&2; exit 2;;
esac
