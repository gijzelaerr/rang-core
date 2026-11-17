#!/usr/bin/env bash
# Validation 2 of research/e2-average-time.md, every step under the heavy lock
# (one acquisition per step). From Git Bash on Windows:
#   bash e2avg_luno_all.sh 'D:\rang\outputs\e2-20261110-11-avg'
set -u
RUN="$1"
WT="$(cd "$(dirname "$0")/../../.." && pwd -W)"
PY="$WT/.venv/Scripts/python.exe"
S="$WT/research/results/e2-average-time/e2avg_luno.py"
LOCK="C:/Users/gijsm/Github/rang/tools/heavy_lock.py"  # the main checkout's FIFO queue (origin/main bd15126)
export PYTHONPATH="$WT/python"
for step in build readable rang casa score; do
  if [ -f "$RUN/luno-$step.done" ]; then continue; fi
  echo "$(date -Is) start $step" >> "$RUN/luno-all.log"
  "$PY" "$LOCK" run -- "$PY" "$S" "$step" "$RUN" > "$RUN/luno-$step.stdout" 2>&1
  rc=$?
  echo "$(date -Is) end $step rc=$rc" >> "$RUN/luno-all.log"
  if [ $rc -ne 0 ]; then exit $rc; fi
  touch "$RUN/luno-$step.done"
done
