#!/usr/bin/env bash
# run1.sh BIN TAG SKY FORM [extra gemclean options...]
#   SKY  s1 s2 s3 h1 h2 h3 h4 p256 p512   FORM  def | coarse
#   env MEMREP=1 adds -memory-report (instrumented binaries only); WATCH_GB stops the run at that RSS.
# One GeMClean run under the heavy lock, GNU time -v, load before and after, SHA-256 of the five FITS.
set -u
O=/mnt/d/rang/outputs/20261106-g2-memory
DATA=$HOME/Build/tmp/20261106-g2-memory/data
LOCK=$HOME/.rang-heavy.lock
bin=$1; tag=$2; sky=$3; form=$4; shift 4
case $sky in
  s1|s2|s3|h1|h2|h4) size=2048; scale=1.5; thr=0.0001; ms=$DATA/$sky.ms ;;
  h3) size=4096; scale=1.5; thr=0.0001; ms=$DATA/h3.ms ;;
  p256) size=4096; scale=3; thr=0.003; ms=$DATA/cal2.ms ;;
  p512) size=4096; scale=3; thr=0.003; ms=$DATA/cal.ms ;;
  *) echo "unknown sky $sky"; exit 2 ;;
esac
f=()
[ "$form" = coarse ] && f=(-single -wgridder-accuracy 1e-4)
[ "${MEMREP:-0}" = 1 ] && f+=(-memory-report)
name=$sky-$form
d=$O/runs/$tag
mkdir -p "$d/img" "$d/log" "$d/time" "$d/load"
w=${WATCH_GB:-0}
exec 9>"$LOCK"
flock 9
{ date -Iseconds; cat /proc/loadavg; free -b | sed -n 2,3p; } > "$d/load/$name.txt"
/usr/bin/time -v -o "$d/time/$name.txt" "$bin" -name "$d/img/$name" -size $size $size -scale ${scale}asec \
  -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold $thr -data-column DATA -field 0 -j 16 \
  "${f[@]}" "$@" "$ms" > "$d/log/$name.log" 2>&1 9>&- &
tp=$!
if [ "$w" != 0 ]; then
  limit=$(python3 -c "print(int($w*1e9/1024))")
  ( while kill -0 $tp 2>/dev/null; do
      gp=$(pgrep -P $tp | head -1)
      if [ -n "$gp" ]; then
        rss=$(awk '/VmRSS/{print $2}' /proc/$gp/status 2>/dev/null); rss=${rss:-0}
        echo "$(date +%s) $rss" >> "$d/load/$name.rss"
        if [ "$rss" -gt "$limit" ]; then echo "STOPPED at RSS ${rss} kB" >> "$d/log/$name.log"; kill $gp; fi
      fi
      sleep 1
    done ) &
fi
wait $tp; rc=$?
wait
{ date -Iseconds; cat /proc/loadavg; free -b | sed -n 2,3p; } >> "$d/load/$name.txt"
flock -u 9
exec 9>&-
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time/$name.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time/$name.txt")
sums=$( (cd "$d/img" && for k in dirty psf model residual image; do [ -f "$name-$k.fits" ] && sha256sum "$name-$k.fits"; done) )
echo "$sums" > "$d/img/$name.sha256"
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$sky" "$form" "$rc" "$wall" "$rss" "$(sha256sum "$bin" | cut -c1-12)" >> "$O/runs.tsv"
echo "$tag $name rc=$rc wall=$wall maxrss_kB=$rss"
