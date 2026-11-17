#!/bin/bash
# Family II of research/floor-5.md: one GeMClean arm per call: fam2.sh ARM
source ~/Build/tmp/20261117-floor5/env.sh
A=$1; MS=$OUT/g1/P/pilot.ms; D=$OUT/family2/$A; mkdir -p $D
M=$RANG_FLOOR_HELD/images/source-mask.fits
B="-size 4096 4096 -scale 3asec -weight briggs 0.5 -gain 0.1 -nmiter 1000 -j 8 -wgridder-accuracy 1e-06 -field 0 -no-update-model-required"
case $A in
  R3)    X="-niter 1000000 -threshold 0.003 -data-column CORRECTED_DATA";;
  Dm1)   X="-niter 10000000 -threshold 0.001 -fits-mask $M -data-column CORRECTED_DATA";;
  Dm03)  X="-niter 10000000 -threshold 0.0003 -fits-mask $M -data-column CORRECTED_DATA";;
  Dms03) X="-niter 10000000 -threshold 0.0003 -fits-mask $M -multiscale -data-column CORRECTED_DATA";;
  Du1)   X="-niter 10000000 -threshold 0.001 -data-column CORRECTED_DATA";;
  S)     X="-niter 10000000 -threshold 0.003 -channels-out 8 -join-channels -fit-spectral-pol 2 -data-column CORRECTED_DATA";;
  C0)    X="-niter 10000000 -threshold 0.0003 -fits-mask $M -data-column DATA";;
  *) echo "unknown arm $A"; exit 2;;
esac
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) $A start"
/usr/bin/time -f "$A %e s %M KB" $PY -m rang.gemclean -name $D/image $B $X $MS > $D/gemclean.log 2>&1
rc=$?; tail -4 $D/gemclean.log
echo "== $(date -Is) load $(cut -d" " -f1-3 /proc/loadavg) $A end rc $rc"
