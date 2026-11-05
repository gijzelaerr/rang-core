#!/usr/bin/env bash
# Native WSClean against GeMClean: S1-S3 and the held-out skies, three interleaved repeats.
# Outputs move to D: after each repeat so the WSL disk does not hold them all.
set -u
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
ROOT=/home/gijsm/Github/rang
W=/home/gijsm/Build/tmp/20261104-speed-native
D=/mnt/d/rang/outputs/20261104-speed/native
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
GEM=/mnt/d/rang/outputs/20261104-speed/gemclean-3945394
mkdir -p "$W/data" "$D"
cp "$GEM" "$W/gemclean"
for s in s1 s2 s3; do cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/$s.ms /mnt/d/rang/outputs/20261102-gemclean/bench/data/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/$s.ms /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/$s.json "$W/data/"; done
du -sh "$W/data"
export BENCH_DATA=$W/data BENCH_LOCK=/home/gijsm/.rang-heavy.lock BENCH_WSCLEAN_IMAGE=rang-wsclean-native:3.7
export BENCH_TIMING_DATASETS="s1 s2 s3 h1 h2 h3 h4"
cd /mnt/c/Users/gijsm/Github/rang || exit 3
for rep in 1 2 3; do
  # The script takes REPEATS from 1, and picks the order from the repeat number, so run it per repeat.
  mkdir -p "$W/out/rep$rep"
  for ds in $BENCH_TIMING_DATASETS; do
    for t in 16 1; do
      run=$W/out/rep$rep
      {
        echo "# speed-run status"
        echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"
        echo "Native WSClean pass: repeat $rep of 3, $ds at -j $t"
        echo "Results: none until all repeats are in"
      } > "$STATUS"
      w() { BENCH_THREADS=$t BENCH_MODES=abs BENCH_LOOPS=fast BENCH_GRIDS="minres nominres" bash examples/gemclean_bench_run.sh wsclean "$run/wsclean" "$ds"; }
      g() { BENCH_THREADS=$t BENCH_MODES=abs bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$run/gemclean" "$ds"; }
      if ((rep % 2)); then w; g; else g; w; fi
    done
  done
  BENCH_THREADS=16 BENCH_MODES=abs BENCH_LOOPS=hogbom BENCH_GRIDS=nominres bash examples/gemclean_bench_run.sh wsclean "$W/out/rep$rep/wsclean" s1
  rm -rf "$W/out/rep$rep/wsclean/ms" "$W/out/rep$rep/gemclean/ms"
  cp -r "$W/out/rep$rep" "$D/" && rm -rf "$W/out/rep$rep"
  echo "repeat $rep copied"
done
rm -rf "$W"
echo "finished"
du -sh "$D" | cut -f1
