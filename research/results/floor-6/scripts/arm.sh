#!/bin/bash
# One GeMClean arm of research/floor-6.md section 5: arm.sh NAME
source ~/Build/tmp/20261117-floor6/env.sh
A=$1; M=$HELD/images/source-mask.fits
case $A in p*) MS=$F5/g1/P/pilot.ms; D=$FAM/$A;; *) MS=$HO/P/pilot.ms; D=$FAM/$A;; esac
mkdir -p $D
Bc="-size 4096 4096 -scale 3asec -weight briggs 0.5 -gain 0.1 -nmiter 1000 -j 8 -wgridder-accuracy 1e-06 -field 0 -no-update-model-required"
SP="-channels-out 8 -join-channels -fit-spectral-pol 2"
case ${A#p} in
  R3)    X="-niter 1000000 -threshold 0.003 -data-column CORRECTED_DATA";;
  Dm03)  X="-niter 10000000 -threshold 0.0003 -fits-mask $M -data-column CORRECTED_DATA";;
  C0)    X="-niter 10000000 -threshold 0.0003 -fits-mask $M -data-column DATA";;
  S)     X="-niter 10000000 -threshold 0.003 $SP -data-column CORRECTED_DATA";;
  Dm1)   X="-niter 10000000 -threshold 0.001 -fits-mask $M -data-column CORRECTED_DATA";;
  Rm3)   X="-niter 10000000 -threshold 0.003 -fits-mask $M -data-column CORRECTED_DATA";;
  Sm3)   X="-niter 10000000 -threshold 0.003 -fits-mask $M $SP -data-column CORRECTED_DATA";;
  SDm03) X="-niter 10000000 -threshold 0.0003 -fits-mask $M $SP -data-column CORRECTED_DATA";;
  *) echo "unknown arm $A"; exit 2;;
esac
case "$X" in *multiscale*) echo "multiscale is not allowed"; exit 2;; esac
echo "== $(date -Is) $A start ms $MS"
$PY -m rang.gemclean -name $D/image $Bc $X $MS > $D/gemclean.log 2>&1
rc=$?; tail -4 $D/gemclean.log
echo "== $(date -Is) $A end rc $rc"
exit $rc
