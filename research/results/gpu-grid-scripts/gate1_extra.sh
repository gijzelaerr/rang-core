#!/usr/bin/env bash
# Gate 1 extras: amendment 9.3 (a) dirty images; 9.1 batching (S1 at a 500 MiB budget,
# several batches); fresh-process repeats of S1 coarse at 4096 MiB (two more).
P=$1
D=$(dirname "$0")
bash $D/gate1_dirty.sh $P 4096
bash $D/gate1.sh $P 500 s1
for r in 2 3; do
  O=D:/rang/outputs/20261116-gpu-grid/gate1
  RAYON_NUM_THREADS=8 "$P" D:/rang/outputs/20261102-gemclean/bench/data/s1.ms 2048 1.5 1e-4 single \
    D:/rang/outputs/20261116-gpu-grid/base/s1-coarse-model.fits 4096 > $O/s1-coarse-b4096-r$r.json
  RAYON_NUM_THREADS=8 "$P" D:/rang/outputs/20261102-gemclean/bench/data/s1.ms 2048 1.5 1e-6 double \
    D:/rang/outputs/20261116-gpu-grid/base/s1-fine-model.fits 4096 > $O/s1-fine-b4096-r$r.json
  echo "repeat $r rc $?"
done
