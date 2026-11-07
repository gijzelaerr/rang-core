#!/usr/bin/env bash
# id_run.sh BIN TAG SKY FORM : criterion A, one run of G2's identity set at G2's settings
#   (research/g2-memory.md; G2's run1.sh with this task's paths), heavy lock, GNU time -v,
#   SHA-256 of the five FITS files. SKY s1 s2 s3 h1 h2 h3 h4 p256; FORM def | coarse.
set -u
O=/mnt/d/rang/outputs/20261106-g3-spectral
B=/mnt/d/rang/outputs/20261102-gemclean/bench/data
H=/mnt/d/rang/outputs/20261103-gemclean-heldout
bin=$1; tag=$2; sky=$3; form=$4; shift 4
case $sky in
  s1|s2|s3) size=2048; scale=1.5; thr=0.0001; ms=$B/$sky.ms ;;
  h1|h2|h4) size=2048; scale=1.5; thr=0.0001; ms=$H/sim/data/$sky.ms ;;
  h3) size=4096; scale=1.5; thr=0.0001; ms=$H/sim/data/h3.ms ;;
  p256) size=4096; scale=3; thr=0.003; ms=$H/real/cal2.ms ;;
  *) echo "unknown sky $sky"; exit 2 ;;
esac
f=()
[ "$form" = coarse ] && f=(-single -wgridder-accuracy 1e-4)
name=$sky-$form
d=$O/identity/$tag
mkdir -p "$d/img" "$d/log" "$d/time"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
/usr/bin/time -v -o "$d/time/$name.txt" "$bin" -name "$d/img/$name" -size $size $size -scale ${scale}asec \
  -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold $thr -data-column DATA -field 0 -j 16 \
  "${f[@]}" "$@" "$ms" > "$d/log/$name.log" 2>&1 9>&-
rc=$?
flock -u 9
(cd "$d/img" && for k in dirty psf model residual image; do sha256sum "$name-$k.fits"; done) > "$d/img/$name.sha256"
rm -f "$d"/img/$name-*.fits
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time/$name.txt")
echo "$tag $name rc=$rc maxrss_kB=$rss"
