#!/usr/bin/env bash
# E1's Tricolour 0.2.1 oracle (research/e1-chain.md, 4.2), from WSL:
#   bash e1_tricolour.sh RUN SRC_MS STRATEGY
# Copies SRC_MS into RUN/ms/, runs `tricolour -fs polarisation -dc DATA` with
# STRATEGY in rang-tricolour:0.2.1-e1 under tools/heavy_lock.py, and logs
# START, the output and END with the exit code to RUN/tricolour.log.
set -u
run=$1 src=$2 strategy=$3
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
log=$run/tricolour.log
mkdir -p "$run/ms"
name=$(basename "$src")
echo "START $(date -Is) copy $src" >>"$log"
if [ ! -d "$run/ms/$name" ]; then cp -r "$src" "$run/ms/$name"; fi
cp "$strategy" "$run/strategy.yaml"
echo "START $(date -Is) tricolour" >>"$log"
python3 "$root/tools/heavy_lock.py" run -- docker run --rm -v "$run:/work" \
  rang-tricolour:0.2.1-e1 tricolour -c /work/strategy.yaml -fs polarisation \
  -dc DATA -dpm "/work/ms/$name" >>"$log" 2>&1
rc=$?
echo "END $(date -Is) rc=$rc" >>"$log"
exit $rc
