#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# TS-P1 oracle (research/ts-p1.md, T1 and T2c): WSClean 3.7 snapshot dirty
# images, one per integration, of the residual column of a TS-P1 simulation.
# Runs on the WSL host, on an ext4 copy (never on the 9p input), inside
# rang-wsclean-native:3.7, no network.
#
#   bash wsclean_intervals.sh SRC_MS OUTDIR [THREADS] [INTERVALS]
#
# SRC_MS: the simulation (e.g. /mnt/d/rang/outputs/ts-p1-20261116/tsp1-dev.ms);
# OUTDIR: new ext4 directory; it gets ms/ (the copy), w-tNNNN-dirty.fits,
# wsclean.log and timing.txt ("wall_s max_rss_kb exit"). The -image.fits files
# (equal to the dirty images at -niter 0) are deleted after the run.
set -euo pipefail
src=$1; out=$(realpath -m "$2"); threads=${3:-4}; intervals=${4:-450}
mkdir "$out"
name=$(basename "$src")
cp -r "$src" "$out/$name"
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp \
  -e OMP_NUM_THREADS="$threads" -v "$out:$out" -w "$out" rang-wsclean-native:3.7 \
  /usr/bin/time -f "%e %M %x" -o "$out/timing.txt" \
  wsclean -gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution \
  -size 1024 1024 -scale 4asec -weight natural -pol I -niter 0 \
  -intervals-out "$intervals" -field 3 -data-column RESIDUAL_DATA \
  -no-update-model-required -j "$threads" -name "$out/w" "$out/$name" \
  > "$out/wsclean.log" 2>&1
rm -f "$out"/w-t*-image.fits
cat "$out/timing.txt"
