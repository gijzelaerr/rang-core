#!/bin/sh
# SPDX-License-Identifier: MIT
# P3 of research/gate3c-averaging.md: WSClean 3.7 (rang-wsclean-native:3.7, Docker
# in WSL) on the P3 MS copied to WSL's own disk; E2-N's image-stage settings at
# 3072^2 x 2". Usage (inside WSL): ws_run.sh NAME AUTO_THRESHOLD AUTO_MASK
set -e
D=$HOME/scratch/20261128-gate3c-averaging
NAME=$1; AT=$2; AM=$3
mkdir -p $D/$NAME
docker run --rm --network none --user $(id -u):$(id -g) --tmpfs /tmp -e HOME=/tmp \
  -e OMP_NUM_THREADS=8 -v $D:/work:rw -w /work rang-wsclean-native:3.7 \
  wsclean -name /work/$NAME/ws -size 3072 3072 -scale 2asec -weight briggs 0.5 \
  -niter 1000000 -mgain 0.9 -auto-threshold $AT -auto-mask $AM -multiscale \
  -wgridder-accuracy 1e-4 -channels-out 8 -join-channels -fit-spectral-pol 2 \
  -gridder wgridder -no-min-grid-resolution -no-update-model-required \
  -data-column DATA -j 8 -temp-dir /tmp /work/p3.ms
