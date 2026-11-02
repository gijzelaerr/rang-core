#!/usr/bin/env bash
# The timing subset of the gmclean benchmark, for a quiet host only
# (research/gmclean-benchmark.md, "Timing subset to rerun"): every repeat runs
# each job of both imagers interleaved, WSClean first on odd repeats and gmclean
# first on even ones. It records what examples/gmclean_bench_run.sh records
# (load before, during and after, the busy processes, GNU time -v).
#
# Usage: bash examples/gmclean_bench_timing.sh GMCLEAN_BINARY OUT_DIR [REPEATS]
#   REPEATS defaults to 3. BENCH_TIMING_DATASETS (default "s1 s2 s3") and
#   BENCH_TIMING_THREADS (default "16 1") narrow the subset.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
binary=$(realpath "$1")
out=$(realpath -m "$2")
repeats=${3:-3}
datasets=${BENCH_TIMING_DATASETS:-"s1 s2 s3"}
threads=${BENCH_TIMING_THREADS:-"16 1"}

wsclean() {  # wsclean <run> <dataset> <threads>
  BENCH_THREADS=$3 BENCH_MODES=abs BENCH_LOOPS=fast BENCH_GRIDS="minres nominres" \
    bash "$root/examples/gmclean_bench_run.sh" wsclean "$1/wsclean" "$2"
}
gm() {  # gm <run> <dataset> <threads>
  BENCH_THREADS=$3 BENCH_MODES=abs \
    bash "$root/examples/gmclean_bench_gmclean.sh" "$binary" "$1/gmclean" "$2"
}

for ((rep = 1; rep <= repeats; rep++)); do
  run=$out/rep$rep
  mkdir -p "$run"
  for ds in $datasets; do
    for t in $threads; do
      if ((rep % 2)); then
        wsclean "$run" "$ds" "$t"
        gm "$run" "$ds" "$t"
      else
        gm "$run" "$ds" "$t"
        wsclean "$run" "$ds" "$t"
      fi
    done
  done
done
# One plain-loop timing per repeat, on the first dataset at the first thread count.
first_ds=${datasets%% *}
first_t=${threads%% *}
for ((rep = 1; rep <= repeats; rep++)); do
  BENCH_THREADS=$first_t BENCH_MODES=abs BENCH_LOOPS=hogbom BENCH_GRIDS=nominres \
    bash "$root/examples/gmclean_bench_run.sh" wsclean "$out/rep$rep/wsclean" "$first_ds"
done
echo "## done $out"
