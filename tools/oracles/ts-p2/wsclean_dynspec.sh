#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# TS-P2 oracle (research/ts-p2.md, section 3): WSClean 3.7 dirty images per
# interval and channel group (-intervals-out N -channels-out M) of a residual
# column, or per interval only (M = 1, P1's T1 on the real track). Runs on
# the WSL host on an ext4 copy (never on the 9p input), inside
# rang-wsclean-native:3.7, no network.
#
#   bash wsclean_dynspec.sh SRC_MS OUTDIR FIELD INTERVALS GROUPS SIZE SCALE [THREADS]
#
# SRC_MS is copied to OUTDIR (new, ext4) unless it already lies inside it.
# OUTDIR gets w-tNNNN-GGGG-dirty.fits (GROUPS > 1) or w-tNNNN-dirty.fits,
# wsclean.log and timing.txt ("wall_s max_rss_kb exit"). The -image.fits
# copies (equal to the dirty images at -niter 0) are deleted as they appear.
set -euo pipefail
src=$1; out=$(realpath -m "$2"); field=$3; intervals=$4; groups=$5
size=$6; scale=$7; threads=${8:-8}
mkdir -p "$out"
name=$(basename "$src")
if [ ! -d "$out/$name" ]; then cp -r "$src" "$out/$name"; fi
chan=()
if [ "$groups" -gt 1 ]; then chan=(-channels-out "$groups"); fi
trap 'touch "$out/.done"' EXIT
( while [ ! -e "$out/.done" ]; do rm -f "$out"/w-t*-image.fits; sleep 5; done ) &
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp \
  -e OMP_NUM_THREADS="$threads" -v "$out:$out" -w "$out" rang-wsclean-native:3.7 \
  /usr/bin/time -f "%e %M %x" -o "$out/timing.txt" \
  wsclean -gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution \
  -size "$size" "$size" -scale "$scale" -weight natural -pol I -niter 0 \
  -intervals-out "$intervals" "${chan[@]}" -field "$field" \
  -data-column RESIDUAL_DATA -no-update-model-required -j "$threads" \
  -name "$out/w" "$out/$name" > "$out/wsclean.log" 2>&1
rm -f "$out"/w-t*-image.fits
cat "$out/timing.txt"
