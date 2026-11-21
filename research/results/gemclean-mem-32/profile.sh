#!/bin/bash
# gemclean-mem-32 profile (research/gemclean-mem-32.md section 2), nash, shared:
# GeMClean (main, -memory-report) and WSClean 3.7 on E2-N's J1331+3030 (case Q,
# A5's joined-IQUV argv) and target (case I, the selfcal image's settings).
#   profile.sh ARM...   ARM in gq wq gi wi; outputs in $R/<arm>/
set -u
R=/home/gijs/rang-data/outputs/gemclean-mem-32-20261121
export OMP_NUM_THREADS=4
q_g="-size 2048 2048 -scale 2asec -weight briggs 0.0 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -pol IQUV -join-polarizations -data-column DATA -field 1 -no-update-model-required -j 4"
q_w="-size 2048 2048 -scale 2asec -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations -data-column DATA -gridder wgridder -wgridder-accuracy 0.0001 -no-update-model-required -no-small-inversion -j 4 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -field 1"
i_g="-size 4096 4096 -scale 3asec -weight briggs 0.5 -niter 20000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -fit-spectral-pol 2 -multiscale -average-channels 2 -data-column DATA -field 3 -no-update-model-required -j 4"
i_w="-size 4096 4096 -scale 3asec -weight briggs 0.5 -channels-out 8 -join-channels -fit-spectral-pol 2 -multiscale -data-column DATA -gridder wgridder -wgridder-accuracy 0.0001 -no-update-model-required -no-small-inversion -j 4 -niter 20000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -field 3"
for arm in "$@"; do
  o=$R/$arm; mkdir -p $o/tmp
  case $arm in
    gq) cmd="$R/gemclean-main -name $o/image $q_g -memory-report $R/q.ms" ;;
    wq) cmd="wsclean -name $o/w -temp-dir $o/tmp $q_w $R/q.ms" ;;
    gi) cmd="$R/gemclean-main -name $o/image $i_g -memory-report $R/i.ms" ;;
    wi) cmd="wsclean -name $o/w -temp-dir $o/tmp $i_w $R/i.ms" ;;
  esac
  s=$(date +%s)
  /usr/bin/time -v -o $o/time.txt $cmd > $o/log.txt 2>&1
  echo "$(date -u +%FT%TZ) $arm rc=$? $(( $(date +%s) - s )) s peak $(grep Maximum $o/time.txt)" >> $R/profile.log
  (cd $o && sha256sum *.fits > fits.sha256 2>/dev/null; rm -f *.fits; rm -rf tmp)
done
