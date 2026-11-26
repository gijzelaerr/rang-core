#!/bin/bash
# DL4s stage 3 (research/dl4s-screen.md 2.3, readings 2.4): one block, end to end, on nash.
#   dl4s_block.sh CBID
# Run root R (mode 700); the dl2 per-scan MSs are read only. Every step under the heavy lock,
# nice 19 / ionice -c3; done-markers per step; the concat is deleted at the end.
set -euo pipefail
CBID=$1
R=$HOME/rang-data/outputs/dl4s-stage3-20261124
DL2=$HOME/rang-data/outputs/dl2-data-20261119
WT=$HOME/Worktrees/rang/dl4s-stage3
S=$WT/research/results/dl4s-stage3
PY=$WT/.venv/bin/python
RC=$WT/.venv/bin/rang-core
SIF=$HOME/rang-data/oracle-images/rang-o-casa_6.7.6.14.sif
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
B=$R/blocks/$CBID
MS=$R/concat/$CBID.ms
mkdir -p "$B/done" "$R/concat" "$R/logs"
LOG=$R/logs/$CBID.log
T=$R/logs/timings.tsv
step() { # name slots mem -- command...
  local name=$1 slots=$2 mem=$3; shift 4
  if [ -e "$B/done/$name" ]; then echo "skip $name" >>"$LOG"; return 0; fi
  echo "== $name $(date -u +%FT%TZ)" >>"$LOG"
  local t0=$(date +%s.%N)
  /usr/bin/time -f "%e s %M KB" -o "$B/$name.time" \
    $LOCK --slots "$slots" --mem "$mem" -- nice -n 19 ionice -c3 "$@" >>"$LOG" 2>&1
  local t1=$(date +%s.%N)
  printf "%s\t%s\t%s\t%s\n" "$CBID" "$name" "$(cat "$B/$name.time")" "$(date -u +%FT%TZ)" >>"$T"
  touch "$B/done/$name"
}
cd "$B"
step plan 1 2 -- "$PY" "$S/dl4s_plan.py" "$DL2/manifests/$CBID.json" "$S/../e2n-scripts/e2n.yaml" "$B"
cp --update=none "$S/../e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" "$B/"
if [ ! -e "$B/done/concat" ]; then rm -rf "$MS"; fi
step concat 1 8 -- apptainer exec --containall --env HOME=/tmp --env OMP_NUM_THREADS=1 \
  --bind "$DL2:$DL2:ro" --bind "$R:$R" --bind "$S:$S:ro" --pwd "$R/concat" "$SIF" \
  /opt/casa/bin/python -I "$S/dl4s_concat.py" casa "$B/scans.json" "$MS"
step scans 1 8 -- "$PY" "$S/dl4s_concat.py" scans "$B/scans.json" "$MS"
export RAYON_NUM_THREADS=4
step flag 4 24 -- "$RC" flag "$B/off.yaml" "$MS" --run-dir "$B/run-flag"
export RAYON_NUM_THREADS=2
step cal-off 2 16 -- "$RC" calibrate "$B/off.yaml" "$MS" --run-dir "$B/run-off"
# the on arm starts from the flags the off arm started from (its calibrate flag version)
step restore 1 8 -- "$PY" -c "
import json, sys
from rang import core_writeback
v = json.load(open('$B/run-off/state.json'))['stages']['calibrate'].get('flag_version')
print('restore', v)
if v: core_writeback.restore_flags('$MS', v)
"
step cal-on 2 16 -- "$RC" calibrate "$B/on.yaml" "$MS" --run-dir "$B/run-on"
step screen 1 8 -- "$PY" "$S/dl4s_screen.py" "$B/run-off/calibrate" "$B/run-on/calibrate" "$B/screen.json" --block "$CBID"
if [ -e "$B/done/screen" ] && [ "${KEEP_MS:-0}" != 1 ]; then rm -rf "$MS" "$MS.flagversions"; echo "deleted $MS" >>"$LOG"; fi
echo "== end $(date -u +%FT%TZ)" >>"$LOG"
