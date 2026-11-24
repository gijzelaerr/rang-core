#!/bin/bash
# F7 cost (research/f7-flagger.md, D9b cost gate): F5's Stage 6 protocol (research/f5-flagger.md
# section 10) at kernel level 70, targets only (ESO137 chunk 0, neither validation nor held out),
# method N5 (W4 off), threads 4 and 1; then C2 (peak working set, T and N5, 4 threads, separate
# processes). U5 (untrained) stands for the trained network: weights do not change the work.
# Exclusive under heavy_lock on glacier, 21:00-06:00 (or F7_TIMING_UNTIL's hour in a granted slot);
# a gate refusal (exit 4) waits 15 min and retries. Each finished JSON is a done-marker.
#
# Usage (Git Bash on glacier): bash examples/f7_timing.sh OUT_DIR
set -u
OUT=${1:?out dir}
W=$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)
PY="$W/.venv/Scripts/python.exe"
LOCK=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
mkdir -p "$OUT"
echo "$(date +%FT%T) start at $(git -C "$W" rev-parse --short HEAD)" >> "$OUT/timing.log"
for thr in 4 1; do
  name="c1-eso-0-t$thr-N5"
  [ -f "$OUT/$name.json" ] && grep -q '"reading"' "$OUT/$name.json" && continue
  while true; do
    h=$(date +%H)
    if [ -n "${F7_TIMING_UNTIL:-}" ]; then
      if [ "$h" -ge "$F7_TIMING_UNTIL" ]; then echo "$name: slot ends at $F7_TIMING_UNTIL:00, stop" >> "$OUT/timing.log"; exit 5; fi
    elif [ "$h" -ge 6 ] && [ "$h" -lt 21 ]; then echo "$name: outside 21:00-06:00, stop" >> "$OUT/timing.log"; exit 5; fi
    RAYON_NUM_THREADS=$thr python "$LOCK" run -- "$PY" "$W/examples/f5_cost.py" pairs "$OUT/$name.json" \
      --set eso:0 --arm U5 --level 70 --degree 1 --pairs 5 --gate >> "$OUT/$name.log" 2>&1
    rc=$?
    echo "$(date +%FT%T) $name rc=$rc" >> "$OUT/timing.log"
    [ $rc -eq 0 ] && grep -q '"reading"' "$OUT/$name.json" && break
    [ $rc -eq 4 ] || grep -q '"skipped"' "$OUT/$name.json" && { sleep 900; continue; }
    exit $rc
  done
done
for which in T F5; do
  name="c2-eso-0-$which"
  [ -f "$OUT/$name.json" ] && continue
  RAYON_NUM_THREADS=4 python "$LOCK" run --slots 4 --mem 24 -- "$PY" "$W/examples/f5_cost.py" rss "$OUT/$name.json" \
    --set eso:0 --which $which --arm U5 --level 70 --degree 1 >> "$OUT/$name.log" 2>&1
  echo "$(date +%FT%T) $name rc=$?" >> "$OUT/timing.log"
done
echo "$(date +%FT%T) all done" >> "$OUT/timing.log"
