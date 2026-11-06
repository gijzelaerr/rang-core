#!/usr/bin/env bash
# Run the gemclean benchmark matrix with the gemclean binary
# (research/gemclean-benchmark.md). gemclean has one exact gridder and one loop,
# so the matrix is the threshold settings by thread counts; the job names keep
# the "nominres-fast" labels of the WSClean jobs it is compared with. gemclean
# has no -auto-mask, so its "auto" is -auto-threshold 3 alone.
#
# Usage: bash examples/gemclean_bench_gemclean.sh BINARY RUN_DIR [DATASET ...]
# Environment as examples/gemclean_bench_run.sh (BENCH_THREADS, BENCH_MODES,
# BENCH_FILTER, BENCH_DATA); GEMCLEAN_ARGS adds options, for example -audit.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
binary=$(realpath "$1")
run=$2
shift 2
export BENCH_GRIDS=nominres BENCH_LOOPS=fast
export BENCH_TEMPLATE="$binary -name {out} -size {size} {size} -scale {scale}asec -weight briggs 0.5 \
-niter {niter} -gain 0.1 -nmiter 1000 {threshold_args} -data-column {datacol} -field {field} \
-j {threads} -no-update-model-required ${GEMCLEAN_ARGS:-} {ms}"
exec bash "$root/examples/gemclean_bench_run.sh" gemclean "$run" "$@"
