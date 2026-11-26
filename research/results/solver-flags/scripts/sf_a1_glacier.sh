#!/bin/bash
# solver-flags: A1's arms R, M0, M1, M2 on glacier (Git Bash), moved from nash on 2026-11-25
# (nash's queue blocked on memory). Shards with done-markers under D:/rang/outputs.
#   bash sf_a1_glacier.sh gen | arm ARM | all
set -euo pipefail
WT=/c/Users/gijsm/Worktrees/rang/solver-flags
PY=$WT/.venv/Scripts/python.exe
S=$WT/research/results/solver-flags/scripts
R=/d/rang/outputs/solver-flags-20261125
A=$R/a1
LOCK="python /c/Users/gijsm/Github/rang/tools/heavy_lock.py run"
mkdir -p "$R/logs" "$A"
log() { echo "$(date -Is) $*" >> "$R/logs/driver.log"; }
shard() { [ -e "$R/done.$1" ]; }
mark() { touch "$R/done.$1"; log "$1 done"; }
timed() { local name=$1; shift; local t0=$(date +%s); "$@"; echo "$name $(( $(date +%s) - t0 )) s" >> "$R/logs/times.txt"; }
gen() {
  if ! shard a1-gen; then
    timed a1-gen $LOCK --slots 4 --mem 16 -- "$PY" -m rang.simtruth_ms generate full "$A/gen" --workers 4 > "$R/logs/a1-gen.log" 2>&1
    mark a1-gen
  fi
}
arm() {
  local ARM=$1
  if ! shard "a1-cfg-$ARM"; then
    cp "$WT/research/results/e1-chain-scripts/e1_config.yaml" "$A/e1.yaml"
    cp "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$A/"
    cp "$S/../mk_rfi_flagging_mild.yaml" "$A/"
    # memory 12 GiB inside a 16 GB booking (glacier's free memory); results do not depend on it.
    "$PY" -I "$S/sf_cfg.py" "$A/e1.yaml" "$A/a1-$ARM.yaml" "$ARM" 12
    mark "a1-cfg-$ARM"
  fi
  if ! shard "a1-copy-$ARM"; then
    rm -rf "$A/a1-$ARM.ms" "$A/a1-$ARM.ms.flagversions" "$A/a1-$ARM.ms.rang-run"
    cp -r "$A/gen/a1-full.ms" "$A/a1-$ARM.ms"; mark "a1-copy-$ARM"
  fi
  if ! shard "a1-run-$ARM"; then
    log "a1-run-$ARM start $(git -C "$WT" rev-parse --short HEAD)"
    timed "a1-run-$ARM" $LOCK --slots 4 --mem 16 -- env RAYON_NUM_THREADS=4 "$PY" -m rang.core_cli run "$A/a1-$ARM.yaml" "$A/a1-$ARM.ms" > "$R/logs/a1-run-$ARM.log" 2>&1
    grep -q "apply: done" "$R/logs/a1-run-$ARM.log" && mark "a1-run-$ARM"
  fi
}
case ${1:-} in
gen) gen ;;
arm) arm "$2" ;;
all) gen; for a in R M0 M1 M2; do arm $a || echo "$(date -Is) FAILED a1-$a" >> "$R/logs/FAILED"; done ;;
*) echo "usage: sf_a1_glacier.sh gen|arm ARM|all" >&2; exit 2;;
esac
