#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# TS-P1 T6 on the shared host nash (research/ts-p1.md 13.4, amended 15.8):
# rang-core lightcurve against WSClean 3.7 -intervals-out on tsp1-held2, three
# readings each, in the order R W W R R W, under one exclusive heavy-lock hold:
#
#   nice -n 19 ionice -c3 python3 ~/Github/rang/tools/heavy_lock.py run -- \
#     bash tools/oracles/ts-p1/t6_nash.sh DATA WORK WSCLEAN [ORDER]
#
# DATA: holds tsp1-held2.ms and tsp1-held2.positions.csv (read only).
# WORK: new directory; gets wsc-ms/ (WSClean's copy, untimed), lc-t6-rN/ and
# wsc-t6-wN/ (logs; WSClean's FITS are deleted after each reading) and
# readings.jsonl (tools/oracles/nash/timed.py). WSCLEAN: the binary built on
# nash with tools/oracles/wsclean-native/Dockerfile's recipe. Settings are
# those of wsclean_intervals.sh and t6_run.py, at 16 threads.
set -euo pipefail
data=$(realpath "$1"); work=$(realpath -m "$2"); ws=$(realpath "$3")
order=${4:-"R W W R R W"}
here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../../.." && pwd)
py=$checkout/.venv/bin/python
timed="$py $checkout/tools/oracles/nash/timed.py --out $work/readings.jsonl"
mkdir -p "$work"
{ git -C "$checkout" rev-parse HEAD; git -C "$checkout" status --short;
  sha256sum "$checkout"/python/rang/_core*.so "$ws"; } > "$work/code.txt"
if [ ! -d "$work/wsc-ms/tsp1-held2.ms" ]; then
  mkdir -p "$work/wsc-ms"; cp -r "$data/tsp1-held2.ms" "$work/wsc-ms/"
fi
warm() { find "$1" -type f -exec cat {} + > /dev/null; }
# Readings are numbered on from earlier calls, so a void reading's repeat
# (ORDER "R" or "W") gets the next number and nothing is overwritten.
nr=$(find "$work" -maxdepth 1 -name 'lc-t6-r*' -type d | wc -l)
nw=$(find "$work" -maxdepth 1 -name 'wsc-t6-w*' -type d | wc -l)
for arm in $order; do
  if [ "$arm" = R ]; then
    nr=$((nr + 1)); out=$work/lc-t6-r$nr
    warm "$data/tsp1-held2.ms"
    RAYON_NUM_THREADS=16 $timed --label "rang-r$nr" --log "$work/lc-t6-r$nr.log" -- \
      "$py" -m rang.core_cli lightcurve "$data/tsp1-held2.ms" --field 3 \
      --positions "$data/tsp1-held2.positions.csv" --size 2048 --scale 2asec \
      --out "$out"
  else
    nw=$((nw + 1)); out=$work/wsc-t6-w$nw
    mkdir "$out"; warm "$work/wsc-ms/tsp1-held2.ms"
    # As wsclean_intervals.sh: the -image.fits copies are removed as they appear.
    ( while [ ! -e "$out/.done" ]; do rm -f "$out"/w-t*-image.fits; sleep 5; done ) &
    OMP_NUM_THREADS=16 $timed --label "wsclean-w$nw" --cwd "$out" --log "$out/wsclean.log" -- \
      "$ws" -gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution \
      -size 2048 2048 -scale 2asec -weight natural -pol I -niter 0 \
      -intervals-out 450 -field 3 -data-column RESIDUAL_DATA \
      -no-update-model-required -j 16 -name "$out/w" "$work/wsc-ms/tsp1-held2.ms" || true
    touch "$out/.done"; wait
    rm -f "$out"/w-t*-image.fits "$out"/w-t*-dirty.fits
  fi
done
echo "t6 readings done: $work/readings.jsonl"
