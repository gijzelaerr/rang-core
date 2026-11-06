#!/usr/bin/env bash
# Copy the seven skies and the two pilot sets to the WSL disk (faster reads than /mnt/d).
set -eu
D=$HOME/Build/tmp/20261106-g2-memory/data
mkdir -p $D
for s in s1 s2 s3; do [ -d $D/$s.ms ] || cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/$s.ms $D/; done
for s in h1 h2 h3 h4; do [ -d $D/$s.ms ] || cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/$s.ms $D/; done
for s in cal cal2; do [ -d $D/$s.ms ] || cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/real/$s.ms $D/; done
du -sh $D/*
