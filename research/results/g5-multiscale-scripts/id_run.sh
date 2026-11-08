#!/usr/bin/env bash
# id_run.sh BIN TAG RUN FORM : criterion A of research/g5-multiscale.md, one run without
# -multiscale, at the settings of the reference, heavy lock, GNU time -v, SHA-256 of every FITS file.
#   RUN s1 s2 s3 h1 h2 h3 h4 p256 (G2's identity set, FORM def | coarse) or D1-C1, D1-C3 (G3's
#   development runs, FORM def).
set -u
O=${G5_ID_OUT:-/mnt/d/rang/outputs/g5-20261107-02}
B=/mnt/d/rang/outputs/20261102-gemclean/bench/data
H=/mnt/d/rang/outputs/20261103-gemclean-heldout
G3=/mnt/d/rang/outputs/20261106-g3-spectral/data
bin=$1; tag=$2; run=$3; form=$4; shift 4
extra=()
case $run in
  s1|s2|s3) size=2048; scale=1.5; thr=0.0001; ms=$B/$run.ms ;;
  h1|h2|h4) size=2048; scale=1.5; thr=0.0001; ms=$H/sim/data/$run.ms ;;
  h3) size=4096; scale=1.5; thr=0.0001; ms=$H/sim/data/h3.ms ;;
  p256) size=4096; scale=3; thr=0.003; ms=$H/real/cal2.ms ;;
  D1-C1) size=2048; scale=1.5; thr=0.00015; ms=$G3/D1.ms; extra=(-channels-out 8 -join-channels -fit-spectral-pol 4) ;;
  D1-C3) size=2048; scale=1.5; thr=0.0003; ms=$G3/D1.ms; extra=(-channels-out 4) ;;
  *) echo "unknown run $run"; exit 2 ;;
esac
f=()
[ "$form" = coarse ] && f=(-single -wgridder-accuracy 1e-4)
name=$run-$form
d=$O/identity/$tag
mkdir -p "$d/img" "$d/log" "$d/time"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
/usr/bin/time -v -o "$d/time/$name.txt" "$bin" -name "$d/img/$name" -size $size $size -scale ${scale}asec \
  -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold $thr -data-column DATA -field 0 -j 16 \
  "${extra[@]}" "${f[@]}" "$@" "$ms" > "$d/log/$name.log" 2>&1 9>&-
rc=$?
flock -u 9
(cd "$d/img" && for k in "$name"-*.fits; do sha256sum "$k"; done) > "$d/img/$name.sha256"
rm -f "$d"/img/$name-*.fits
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time/$name.txt")
echo "$tag $name rc=$rc maxrss_kB=$rss"
