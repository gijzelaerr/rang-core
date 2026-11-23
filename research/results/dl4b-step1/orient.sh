#!/bin/bash
# DL4b step 1, pre-freeze orientation (glacier WSL): two throwaway skies (H4, H5 recipes,
# orientation seeds 990001/990002, never reused), W1 timed, -continue tested, CAN-48 pass timed.
set -u
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
O=/mnt/d/rang/dl4b-step1/orient; mkdir -p $O; cd $O
PY=$HOME/Github/rang/.venv/bin/python
WS="docker run --rm --user $(id -u):$(id -g) -v /mnt/d:/mnt/d -v /dev/shm:/dev/shm -w $O rang-wsclean-native:3.7 wsclean"
W1="-size 4096 4096 -scale 1.5asec -weight briggs 0.5 -j 16 -niter 10000000 -no-update-model-required -multiscale -auto-mask 5 -auto-threshold 3 -mgain 0.8"
for s in H4 H5; do
  [ -d $s.ms ] || /usr/bin/time -f "$s simulate wall %e s rss %M KB" $PY $H/examples/gemclean_bench_simulate.py $s.ms --sky $s --size 4096 --sky-seed 99000${s#H} --noise-seed 99100${s#H} --catalogue $s.json 2>&1 | tail -2
  /usr/bin/time -f "$s W1 wall %e s" $WS $W1 -name $s-W1 $s.ms > $s-W1.log 2>&1; tail -1 $s-W1.log
  grep -E "Inversion:|major iterations|iterations in total" $s-W1.log | tail -3
done
# -continue: H5, W1 stopped after 1 major iteration, then continued with W1's settings
$WS $W1 -nmiter 1 -name H5-c $O/H5.ms > H5-c1.log 2>&1; grep -E "Inversion:|major" H5-c1.log | tail -2
cp H5-c-model.fits H5-c-model-after1.fits
/usr/bin/time -f "H5 continue wall %e s" $WS $W1 -continue -name H5-c $O/H5.ms > H5-c2.log 2>&1; tail -1 H5-c2.log; grep -E "Inversion:|major|iterations in total|rror" H5-c2.log | tail -4
$PY - <<PY
from astropy.io import fits; import numpy as np
a=fits.getdata("$O/H5-W1-model.fits").squeeze(); b=fits.getdata("$O/H5-c-model.fits").squeeze()
ra=fits.getdata("$O/H5-W1-residual.fits").squeeze(); rb=fits.getdata("$O/H5-c-residual.fits").squeeze()
print("continue vs full: model flux", float(a.sum()), float(b.sum()), "residual rms", float(ra.std()), float(rb.std()))
PY
