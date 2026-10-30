#!/bin/bash
# CARACal first-pass calibrator strategy (Tricolour 0.2.1) on scan 9: native flags and widened to 60 %.
set -u
S=$(cd "$(dirname "$0")" && pwd)
B=~/Build/tmp/20261030-upstream-prs
G=$B/guard
P=$B/venv-tric021/bin/python
STRAT=$B/caracal/caracal/data/meerkat_files/mk_rfi_flagging_calibrator_fields_firstpass.yaml
mkdir -p $G && cd $G
git -C $B/caracal show 1.2.1:caracal/data/meerkat_files/mk_rfi_flagging_calibrator_fields_firstpass.yaml > firstpass-1.2.1.yaml
cmp firstpass-1.2.1.yaml $STRAT && echo "strategy identical in 1.2.1 and master"
export NUMBA_CACHE_DIR=$G/numba-cache
for arm in native pre60; do
  rm -rf $arm.ms && cp -r $B/conv/scan9.ms $arm.ms
  [ $arm = pre60 ] && $P "$S/bins.py" --preflag $arm.ms 0.60
  $P "$S/bins.py" --save $arm.ms $arm-before.npy
  # script gives tricolour a TTY, so it does not wait on ProgressBar(dt=300) (tricolour#110)
  script -qec "/usr/bin/time -f '$arm tricolour wall %e s maxrss %M KB' $B/venv-tric021/bin/tricolour \
    -c firstpass-1.2.1.yaml -fs polarisation -dc DATA -wb numpy -fn J1939-6342 -dpm $arm.ms" /dev/null > $arm-tricolour.log 2>&1
  grep "wall" $arm-tricolour.log
  for iv in "2 32" "1 1"; do $P "$S/bins.py" $arm-before.npy $arm.ms $iv > $arm-bins-${iv// /x}.json; done
done
