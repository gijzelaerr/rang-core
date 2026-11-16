#!/usr/bin/env bash
# WSClean 3.7 (rang-wsclean-native:3.7), plain and fast loops, on the new skies H5-H8 of
# research/gemclean-stop28.md, from WSL; each sky holds the shared heavy lock of the main
# checkout per loop: the fast loop 8 slots, the plain (Hogbom) loop 3 (it used about 2.2 cores
# at -j 8 on H5, its minor loop being serial). Usage: bash examples/stop28_wsclean.sh [h5 h6 h7 h8]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
O=${O:-/mnt/d/rang/outputs/stop28-20261116}
lock=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
skies=("$@"); [ ${#skies[@]} -eq 0 ] && skies=(h5 h6 h7 h8)
for ds in "${skies[@]}"; do
  for loop in fast hogbom; do
    slots=8; [ $loop = hogbom ] && slots=3
    python3 "$lock" run --slots $slots --mem 8 -- env BENCH_DATA="$O/data" BENCH_MODES=abs       BENCH_GRIDS=nominres BENCH_LOOPS=$loop BENCH_THREADS=8       BENCH_LOCK=/tmp/stop28-bench.lock BENCH_WSCLEAN_IMAGE=rang-wsclean-native:3.7       bash "$here/gemclean_bench_run.sh" wsclean "$O/wsclean" "$ds"
  done
done
echo WSCLEAN-DONE
