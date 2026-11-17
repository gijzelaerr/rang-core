#!/bin/bash
# WSClean on a read-only MS with -no-update-model-required: contiguous (-no-reorder) vs reordered.
# Usage (in WSL): bash readonly_ms.sh <dir holding the MS> <ms name> <log dir>
set -u
MSDIR=$1; MS=$2; LOG=$3
common="-size 512 512 -scale 2asec -niter 200 -no-update-model-required -j 2"
for arm in "noreorder-mgain0.8:-no-reorder -mgain 0.8" "noreorder-mgain1:-no-reorder -mgain 1" \
           "noreorder-mgain1-nmiter2:-no-reorder -mgain 1 -nmiter 2" \
           "reorder-mgain0.8:-reorder -mgain 0.8" "default-mgain0.8:-mgain 0.8"; do
  name=${arm%%:*}; flags=${arm#*:}
  s=$(date +%s.%N)
  docker run --rm --network none -v "$MSDIR":/ms:ro rang-wsclean-native:3.7 \
    bash -c "cd /tmp && wsclean $common $flags -temp-dir /tmp -name /tmp/$name /ms/$MS" \
    > "$LOG/ro-$name.log" 2>&1
  rc=$?
  e=$(date +%s.%N)
  printf "%s rc=%s wall=%.1fs | %s | %s\n" "$name" "$rc" "$(echo "$e - $s" | bc)" \
    "$(grep -m1 -E 'iterations in total' "$LOG/ro-$name.log")" \
    "$(grep -m1 -i 'read/write' "$LOG/ro-$name.log")"
done
