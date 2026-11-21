#!/bin/bash
# F6 cost (research/f6-flagger.md section 3, Amendment 2d-2), F5 Stage 6 protocol (research/f5-flagger.md section 10): the one exclusive timing run
# on glacier, from 21:00 SAST. Per set (LUNO MAIN_1 for calibrators, ESO137
# chunk 0 for targets), thread count (4, 1) and candidate method (N5, N5W4 at
# kappa 5), `f5_cost.py pairs --gate`: 5 alternating pairs against T. The
# weights do not change the work, so U5 (untrained) stands for the trained
# network; the method fixed at Stage 4 picks its row. A gate refusal (exit 4:
# other processes above one logical CPU over 10 s) waits 15 min and retries,
# until 06:00 (or F6_TIMING_UNTIL's hour in a granted slot). Each finished JSON is a done-marker; a rerun skips it.
#
# Usage (Git Bash on glacier): bash examples/f6_timing.sh OUT_DIR
set -u
OUT=${1:?out dir}
W=$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)
PY="$W/.venv/Scripts/python.exe"
LOCK=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
mkdir -p "$OUT"
for set in luno:MAIN_1 eso:0; do
  for thr in 4 1; do
    for arm in N5 N5W4; do
      name="c1-${set/:/-}-t$thr-$arm"
      [ -f "$OUT/$name.json" ] && grep -q '"reading"' "$OUT/$name.json" && continue
      while true; do
        h=$(date +%H)
        if [ -n "${F6_TIMING_UNTIL:-}" ]; then  # a granted daytime slot (coordinator), until this hour
          if [ "$h" -ge "$F6_TIMING_UNTIL" ]; then echo "$name: slot ends at $F6_TIMING_UNTIL:00, stop" >> "$OUT/timing.log"; exit 5; fi
        elif [ "$h" -ge 6 ] && [ "$h" -lt 21 ]; then echo "$name: outside 21:00-06:00, stop" >> "$OUT/timing.log"; exit 5; fi
        kap=(); [ "$arm" = N5W4 ] && kap=(--kappa 5)
        RAYON_NUM_THREADS=$thr python "$LOCK" run -- "$PY" "$W/examples/f5_cost.py" pairs "$OUT/$name.json" \
          --set "$set" --arm U5 --level 20 --degree 1 "${kap[@]}" --pairs 5 --gate >> "$OUT/$name.log" 2>&1
        rc=$?
        echo "$(date +%FT%T) $name rc=$rc" >> "$OUT/timing.log"
        [ $rc -eq 0 ] && break
        [ $rc -eq 4 ] && { sleep 900; continue; }
        exit $rc
      done
    done
  done
done
echo "$(date +%FT%T) all done" >> "$OUT/timing.log"
