#!/usr/bin/env bash
# E6: -beam-band on and off with the same binary, interleaved, three repeats, S1, H2, H3, -j 16 and -j 1.
set -u
O=/mnt/d/rang/outputs/20261104-speed
W=/home/gijsm/Build/tmp/20261105-opt6
BIN=$O/opt/e5/gemclean-band
LOCK=/home/gijsm/.rang-heavy.lock
OUT=$O/opt/e6
mkdir -p "$W" "$OUT"
cp "$BIN" "$W/gemclean"
cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/s1.ms "$W/"
cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/h2.ms /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/h3.ms "$W/"
one() { # sky size j label flag rep
  n=$1-j$3-$4-r$6
  flock $LOCK /usr/bin/time -f "$n wall %e user %U sys %S rss_kb %M" "$W/gemclean" -name "$W/$n" -size "$2" "$2" -scale 1.5asec -weight briggs 0.5 \
    -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j "$3" \
    -single -wgridder-accuracy 1e-4 $5 "$W/$1.ms" > "$OUT/$n.log" 2>&1
  tail -1 "$OUT/$n.log"
  grep 'components,' "$OUT/$n.log" | sed 's/.*major cycles, //' | cut -c1-150
  cat /proc/loadavg
  rm -f "$W/$n"-*.fits
}
for r in 1 2 3; do
  for s in "s1 2048" "h2 2048" "h3 4096"; do
    set -- $s
    for j in 16 1; do
      if ((r % 2)); then one $1 $2 $j off "" $r; one $1 $2 $j on -beam-band $r
      else one $1 $2 $j on -beam-band $r; one $1 $2 $j off "" $r; fi
    done
  done
done
rm -rf "$W"
echo finished
