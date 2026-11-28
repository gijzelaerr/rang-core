#!/usr/bin/env bash
# lane.sh ARM... : loops one after another (8 slots, 20 GB each); "AX" runs the AX solve
R=D:/rang/outputs/dd14-20261127; S=tools/oracles/dd14/dd14.py
for a in "$@"; do
  if [ "$a" = AX ]; then bash $R/scripts/job.sh ax 8 20 -- $S ax $R || exit 1
  else bash $R/scripts/job.sh loop-$a 8 20 -- $S loop $R $a || exit 1; fi
done
