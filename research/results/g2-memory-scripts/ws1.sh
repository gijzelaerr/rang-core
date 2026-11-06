#!/usr/bin/env bash
# ws1.sh SKY GRID : WSClean 3.7 (rang-wsclean-native:3.7) at GeMClean's settings; GNU time -v inside the container.
#   GRID nominres (-no-min-grid-resolution -wgridder-accuracy 1e-6, matches GeMClean's default form)
#        minres   (WSClean's defaults, accuracy 1e-4; set against the coarse form)
# WSClean's memory budget is its default (no -mem, no -abs-mem).
set -u
O=/mnt/d/rang/outputs/20261106-g2-memory
DATA=$HOME/Build/tmp/20261106-g2-memory/data
LOCK=$HOME/.rang-heavy.lock
sky=$1; grid=$2
case $sky in
  s1|s2|s3|h1|h2|h4) size=2048; scale=1.5; thr=0.0001; ms=$sky.ms ;;
  h3) size=4096; scale=1.5; thr=0.0001; ms=h3.ms ;;
  p256) size=4096; scale=3; thr=0.003; ms=cal2.ms ;;
  p512) size=4096; scale=3; thr=0.003; ms=cal.ms ;;
esac
g=()
[ "$grid" = nominres ] && g=(-no-min-grid-resolution -wgridder-accuracy 1e-6)
name=$sky-$grid
d=$O/runs/wsclean
mkdir -p "$d/img" "$d/log" "$d/time" "$d/load" "$d/tmp"
exec 9>"$LOCK"
flock 9
{ date -Iseconds; cat /proc/loadavg; free -b | sed -n 2,3p; } > "$d/load/$name.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 \
  -v "$DATA:/data:ro" -v "$d:/run" -w /run rang-wsclean-native:3.7 \
  /usr/bin/time -v -o "/run/time/$name.txt" \
  wsclean -gridder wgridder -data-column DATA -field 0 -size $size $size -scale ${scale}asec -weight briggs 0.5 -pol I \
  -j 16 -no-update-model-required -temp-dir /run/tmp -niter 1000000 -nmiter 0 -gain 0.1 -mgain 0.8 -abs-threshold $thr \
  "${g[@]}" -name "/run/img/$name" "/data/$ms" > "$d/log/$name.log" 2>&1 9>&-
rc=$?
{ date -Iseconds; cat /proc/loadavg; free -b | sed -n 2,3p; } >> "$d/load/$name.txt"
flock -u 9
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time/$name.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time/$name.txt")
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' wsclean "$sky" "$grid" "$rc" "$wall" "$rss" rang-wsclean-native:3.7 >> "$O/runs.tsv"
rm -f "$d"/img/$name-*-dirty.fits "$d"/img/$name-psf.fits
echo "wsclean $name rc=$rc wall=$wall maxrss_kB=$rss"
