#!/bin/bash
set -u
B=$1; O=$2; MS=D:/rang/outputs/gemclean-memory-20261115/s16.ms
for r in a b; do mkdir -p $O/$r
"$B" -name $O/$r/g -size 512 512 -scale 4asec -weight briggs 0 -niter 100000 -mgain 0.9 -auto-threshold 3 -auto-mask 5 \
  -wgridder-accuracy 1e-4 -data-column DATA -no-update-model-required -pol IQUV -join-polarizations \
  -channels-out 4 -join-channels -j 4 $MS > $O/$r.out 2>&1
(cd $O/$r && sha256sum *.fits > ../$r.sha)
done
cmp $O/a.sha $O/b.sha && echo IDENTICAL
