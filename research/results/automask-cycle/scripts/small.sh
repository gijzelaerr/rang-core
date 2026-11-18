#!/bin/bash
# small.sh G|W GROUP NMITER [extra args]: SDa settings (sdm03 W-SDa / SDa argv) with -nmiter, 8 threads, under the lock
source ~/Build/tmp/20261118-automask-cycle/env.sh
who=$1; g=$2; nm=$3; shift 3
r=$OUT/r-$g; ms=$r/P/pilot.ms
name=$who-$g-n$nm${TAG:+-$TAG}; d=$OUT/small/$name; mkdir -p $d/tmp
COMMON="-size 4096 4096 -scale 3asec -weight briggs 0.0 -niter 1000000 -mgain 0.9 -auto-threshold 0.5 -auto-mask 6.0 -channels-out 8 -join-channels -fit-spectral-pol 2 -data-column CORRECTED_DATA -field 0 -no-update-model-required"
if [ $who = W ]; then
  cmd="/usr/bin/wsclean -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 0.0001 -name $d/image $COMMON -nmiter $nm -pol I -j 8 -temp-dir $d/tmp $* $ms"
  mem=12
else
  cmd="$PY -m rang.gemclean -name $d/image $COMMON -wgridder-accuracy 0.0001 -j 8 -nmiter $nm $* $ms"
  mem=24
fi
[ "$nm" = 0 ] && cmd=${cmd/-nmiter 0/}
echo "$cmd" > $d/argv.txt
$LOCK run --slots 8 --mem $mem -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8 /usr/bin/time -f "TIME $name %e s %M KB" $cmd > $d/imager.log 2>&1
rc=$?
printf "%s\t8\t%s\t%s\t%s\n" "$name" "$mem" "$rc" "$(grep "^TIME" $d/imager.log | tail -1)" >> $OUT/timing.tsv
echo "$(date -Is) small $name rc $rc" >> $LOGS/driver.log
