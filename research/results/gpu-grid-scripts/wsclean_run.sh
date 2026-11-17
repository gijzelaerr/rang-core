#!/usr/bin/env bash
# One WSClean 3.7 (rang-wsclean-native:3.7, built for this CPU) run of issue #12's timing
# (research/gpu-grid.md section 5), in WSL. Usage: wsclean_run.sh SKY MGAIN REP
# Run inside: python3 ~/Github/rang/tools/heavy_lock.py run -- bash wsclean_run.sh ...
set -u
sky=$1; mgain=$2; rep=$3
R=$HOME/Build/tmp/20261116-gpu-grid
OUT=/mnt/d/rang/outputs/20261116-gpu-grid/wsclean
size=2048; [ "$sky" = h3 ] && size=4096
name=$sky-minres-mgain$mgain-r$rep
mkdir -p "$R/run/tmp" "$R/run/timing" "$OUT"
[ -d "$R/run/$sky.ms" ] || cp -r "$R/ms/$sky.ms" "$R/run/"
cat /proc/loadavg > "$OUT/$name.load"
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 \
  -v "$R/run:/run" -w /run rang-wsclean-native:3.7 /usr/bin/time -v -o "/run/timing/$name.txt" \
  wsclean -gridder wgridder -data-column DATA -field 0 -size $size $size -scale 1.5asec \
  -weight briggs 0.5 -pol I -j 16 -no-update-model-required -temp-dir /run/tmp \
  -niter 1000000 -nmiter 0 -gain 0.1 -mgain "$mgain" -abs-threshold 0.0001 \
  -name "/run/$name" "/run/$sky.ms" > "$OUT/$name.log" 2>&1
rc=$?
cat /proc/loadavg >> "$OUT/$name.load"
cp "$R/run/timing/$name.txt" "$OUT/"
mv "$R/run/$name-model.fits" "$R/run/$name-residual.fits" "$R/run/$name-image.fits" "$OUT/" 2>/dev/null
rm -f "$R/run/$name"-*.fits
w=$(grep "Elapsed (wall" "$OUT/$name.txt" | awk '{print $NF}')
m=$(grep "Maximum resident" "$OUT/$name.txt" | awk '{print $NF}')
echo "$name exit $rc wall $w rss_kb $m"
