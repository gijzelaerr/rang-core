#!/bin/bash
# F5 on nash (research/f5-flagger.md, sections 10 and 12): one step at a time
# under nash's heavy lock, nice 19 + ionice -c3, RAYON_NUM_THREADS equal to the
# slots booked, a done-marker per step. Inputs under the run root's d/
# (a copy of D:/rang's layout); outputs under runs/.
#
# Usage: bash examples/f5_nash.sh STEP [class]
#   STEP: crosshost | degree | stage2 | shards-validation | shards-train | tau | heldout | sim
set -eu
source ~/.rang-env.sh
STEP=$1
K=${2:-calibrator}
W=$(cd "$(dirname "$0")/.." && pwd)
R=$HOME/rang-data/outputs/dl3-f5-20261119
D=$R/d
RUNS=$R/runs
SIF=$R/images/rang-aflag-aoflagger_3.5.0.sif
PY=$W/.venv/bin/python
SLOTS=${SLOTS:-8}
MEM=${MEM:-32}
export RAYON_NUM_THREADS=$SLOTS OMP_NUM_THREADS=1
mkdir -p "$RUNS"
cd "$W"
run() {  # name, command...
  local name=$1; shift
  [ -f "$RUNS/$name.done" ] && { echo "$name done already"; return 0; }
  git -C "$W" log -1 --format=%H > "$RUNS/$name.commit"
  /usr/bin/time -f "wall %e s rss %M KB" -o "$RUNS/$name.time" \
    python3 "$HOME/Github/rang/tools/heavy_lock.py" run --slots "$SLOTS" --mem "$MEM" -- \
    nice -n 19 ionice -c3 "$@" > "$RUNS/$name.log" 2>&1
  touch "$RUNS/$name.done"
  tail -2 "$RUNS/$name.log"
}
CAL=$D/outputs/f4-20261111-06-shards-cal
TGT=$D/outputs/f4-20261111-07-shards-target
FLAGS=$CAL
[ "$K" = target ] && FLAGS=$TGT
degree() { "$PY" -c "import json;print(json.load(open('$RUNS/degree-$K.json'))['degree'])"; }
case $STEP in
  crosshost)
    run crosshost-nash "$PY" examples/f5_crosshost.py save "$RUNS/crosshost-nash-MAIN_7.npz" \
      --set luno:MAIN_7 --data-root "$D" --ao-sif "$SIF" --with-a
    "$PY" examples/f5_crosshost.py compare "$RUNS/crosshost-nash-MAIN_7.npz" \
      "$RUNS/crosshost-glacier-MAIN_7.npz" "$RUNS/crosshost-MAIN_7.json" \
      --cached-t "$CAL/calibrator/flags/luno-MAIN_7-T.npy" --cached-a "$CAL/calibrator/flags/luno-MAIN_7-A.npy"
    ;;
  degree)
    run "degree-$K" "$PY" examples/f5_eval.py degree "$RUNS/degree-$K.json" --class "$K" --level 0 --data-root "$D"
    ;;
  stage2)
    run "stage2-$K" "$PY" examples/f5_eval.py stage2 "$RUNS/stage2-$K.json" --class "$K" --level 0 \
      --degree "$(degree)" --flags-from "$FLAGS" --data-root "$D"
    ;;
  shards-validation|shards-train)
    role=${STEP#shards-}
    run "shards-$K-$role" "$PY" examples/f5_shards.py "$RUNS/shards" --class "$K" --role "$role" \
      --level 0 --degree "$(degree)" --flags-from "$FLAGS" --data-root "$D" --ao-sif "$SIF"
    ;;
  tau)
    run "tau-$K" "$PY" examples/f5_tau.py "$RUNS/tau-$K" --class "$K" --weights "$RUNS/train-$K/$(cat "$RUNS/train-$K/median-seed")/weights.npz" \
      --level 0 --degree "$(degree)" --flags-from "$FLAGS" --data-root "$D"
    ;;
  heldout)
    : "${SETS:?set SETS=luno:MAIN_0,luno:MAIN_12,luno:MAIN_14}"
    IFS=, read -r -a sets <<< "$SETS"
    for s in "${sets[@]}"; do
      run "heldout-$K-${s/:/-}" "$PY" examples/f5_heldout.py real "$RUNS/heldout-$K" --set "$s" \
        --method "$RUNS/tau-$K/method.json" --data-root "$D" --ao-sif "$SIF"
    done
    ;;
  sim)
    run "heldout-$K-sim" "$PY" examples/f5_heldout.py sim "$RUNS/heldout-$K" --class "$K" \
      --method "$RUNS/tau-$K/method.json" --data-root "$D"
    ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
