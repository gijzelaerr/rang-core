#!/usr/bin/env bash
# E4: the band-limited resync. -beam-band 0 must reproduce the images of 3945394; then the tolerances.
set -u
O=/mnt/d/rang/outputs/20261104-speed
W=/home/gijsm/Build/tmp/20261104-opt4
BIN=$W/src/core/target/gemclean/gemclean
LOCK=/home/gijsm/.rang-heavy.lock
mkdir -p "$O/opt/e4" "$W/d" "$W/o"
cp "$BIN" "$O/opt/e4/gemclean-band"
cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/s1.ms "$W/d/"
cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/h3.ms "$W/d/"
one() { # sky size j band tau
  n=$1-j$3-b$4-t$5
  flock $LOCK /usr/bin/time -f "$n wall %e rss_kb %M" "$BIN" -name "$W/o/$n" -size "$2" "$2" -scale 1.5asec -weight briggs 0.5 \
    -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j "$3" \
    -single -wgridder-accuracy 1e-4 -beam-band "$4" -tau-min "$5" "$W/d/$1.ms" > "$W/o/$n.log" 2>&1
  tail -1 "$W/o/$n.log"; grep -o '[0-9]* of [0-9]* spectrum columns' "$W/o/$n.log"; grep 'components,' "$W/o/$n.log" | sed 's/.*stop Threshold; //' | cut -c1-140
}
one s1 2048 16 0 0.5
cmp "$W/o/s1-j16-b0-t0.5-model.fits" "$O/opt/e1/single-1e4/rep1/s1-abs-nominres-fast-j16-model.fits" && echo "model identical to 3945394"
cmp "$W/o/s1-j16-b0-t0.5-residual.fits" "$O/opt/e1/single-1e4/rep1/s1-abs-nominres-fast-j16-residual.fits" && echo "residual identical to 3945394"
for b in 1e-7 1e-6 1e-5 1e-4; do one s1 2048 1 $b 0.5; done
one s1 2048 1 0 0.5
for b in 1e-6 1e-5; do one h3 4096 1 $b 0.5; done
one h3 4096 1 0 0.5
cp "$W"/o/*.log "$O/opt/e4/"
cp "$W"/o/s1-j1-*-model.fits "$W"/o/s1-j1-*-residual.fits "$W"/o/*report.json "$O/opt/e4/" 2>/dev/null
rm -rf "$W/o" "$W/d"
echo finished
