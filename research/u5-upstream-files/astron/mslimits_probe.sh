#!/bin/bash
# CalculateMsLimits: w range and max uvw as logged, square vs rectangular images (WSClean 3.7, -niter 0).
# Usage (in WSL): bash mslimits_probe.sh <dir holding the MS> <ms name> <log dir>
set -u
MSDIR=$1; MS=$2; LOG=$3
for sz in "512 512" "2048 128" "128 2048" "64 64"; do
  tag=${sz/ /x}
  docker run --rm --network none -v "$MSDIR":/ms:ro rang-wsclean-native:3.7 bash -c \
    "cd /tmp && wsclean -size $sz -scale 4asec -niter 0 -no-reorder -no-dirty -j 2 -name /tmp/p /ms/$MS" \
    > "$LOG/mslimits-$tag.log" 2>&1
  echo "$tag: $(grep -m1 -E 'maximum uvw' "$LOG/mslimits-$tag.log") | $(grep -m1 -i 'theoretical' "$LOG/mslimits-$tag.log")"
done
