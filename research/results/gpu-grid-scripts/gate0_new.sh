#!/usr/bin/env bash
# Gate 0: the final builds (feature off; feature on without -gpu) on S1 coarse and fine, H3
# coarse, against the a931b6c baseline FITS. Usage: gate0_new.sh REV
REV=$1
W=/c/Users/gijsm/Worktrees/rang/gpu-grid
O=D:/rang/outputs/20261116-gpu-grid
for arm in cpu gpu; do
  for c in "s1 coarse" "s1 fine" "h3 coarse"; do
    set -- $c
    bash $W/outputs/gpu-grid/run_sky.sh $W/outputs/gpu-grid/bin/gemclean-$REV-$arm.exe $O/gate0-$REV-$arm $1-$2 $1 $2 8
  done
done
for arm in cpu gpu; do
  for c in s1-coarse s1-fine h3-coarse; do
    for k in model residual image; do
      a=$(sha256sum < $O/base/$c-$k.fits); b=$(sha256sum < $O/gate0-$REV-$arm/$c-$k.fits)
      [ "$a" = "$b" ] && r=identical || r=DIFFERENT
      echo "$arm $c $k $r"
    done
  done
done
