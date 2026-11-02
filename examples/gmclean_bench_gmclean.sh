#!/usr/bin/env bash
# Run the gmclean benchmark matrix with the gmclean binary
# (research/gmclean-benchmark.md). gmclean has one exact gridder and one loop,
# so the matrix is the threshold settings by thread counts; the job names keep
# the "nominres-fast" labels of the WSClean jobs it is compared with. gmclean
# has no -auto-mask, so its "auto" is -auto-threshold 3 alone.
#
# Usage: bash examples/gmclean_bench_gmclean.sh BINARY RUN_DIR [DATASET ...]
# Environment as examples/gmclean_bench_run.sh (BENCH_THREADS, BENCH_MODES,
# BENCH_FILTER, BENCH_DATA); GMCLEAN_ARGS adds options, for example -audit.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
binary=$(realpath "$1")
run=$2
shift 2
export BENCH_GRIDS=nominres BENCH_LOOPS=fast
export BENCH_TEMPLATE="$binary -name {out} -size {size} {size} -scale {scale}asec -weight briggs 0.5 \
-niter {niter} -gain 0.1 -mgain 0.8 -nmiter 1000 {threshold_args} -data-column {datacol} -field {field} \
-j {threads} ${GMCLEAN_ARGS:-} {ms}"
exec bash "$root/examples/gmclean_bench_run.sh" gmclean "$run" "$@"
