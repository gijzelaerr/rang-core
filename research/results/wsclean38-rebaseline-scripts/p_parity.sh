#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Arm P of research/wsclean38-rebaseline.md: S1 dirty images and PSFs (-niter 0 -make-psf) from
# WSClean 3.7 and 3.8 (glacier's native images), minres and nominres, -j 16. Run from WSL under
# the main checkout's heavy lock (shared, 8 slots); BENCH_LOCK is a private flock file.
set -u
W=$HOME/Build/tmp/20261118-wsclean38-p
O=/mnt/d/rang/outputs/wsclean38-20261118/p
REPO=/mnt/c/Users/gijsm/Worktrees/rang/wsclean-38
mkdir -p "$W/data" "$O"
cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/s1.ms /mnt/d/rang/outputs/20261102-gemclean/bench/data/s1.json "$W/data/"
export BENCH_DATA=$W/data BENCH_LOCK=$W/flock BENCH_THREADS=16 BENCH_MODES=dirty BENCH_LOOPS=fast BENCH_GRIDS="minres nominres"
cd "$REPO" || exit 3
for v in 3.7 3.8; do
  BENCH_WSCLEAN_IMAGE=rang-wsclean-native:$v bash examples/gemclean_bench_run.sh wsclean "$W/out/w$v" s1 | cut -c1-120
  rm -rf "$W/out/w$v/ms"
done
cp -r "$W/out/"* "$O/" && rm -rf "$W"
ls "$O"/*
