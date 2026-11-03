#!/usr/bin/env bash
# One measured run of gram_solver_bench under the heavy lock: perf stat counters,
# GNU time, the load before and after. research/gram-solver.md.
#
#   SOLVER_ROOT=DIR examples/gram_solver_run.sh DATASET NAME MODE [key=value ...]
#
# Output: DIR/runs/NAME.* with timing/NAME.txt and timing/NAME.perf. Threads from
# GRAM_THREADS (default 8, as research/gridder-theory.md).
set -u
ROOT="${SOLVER_ROOT:-$HOME/Build/tmp/20261103-gram-solver}"
BIN="${GRAM_BIN:-core/target/release/gram_solver_bench}"
DATASET="$1"
NAME="$2"
MODE="$3"
shift 3
RUN="$ROOT/runs/$DATASET"
mkdir -p "$RUN/timing" "$RUN/load"
# Done already: nothing to do. GRAM_HELD=1: the caller holds the heavy lock for a
# whole stage, so that a stage is not interleaved job by job with other sessions.
if [ -s "$RUN/timing/$NAME.perf" ]; then
    echo "$NAME: done"
    exit 0
fi
LOCK="flock /home/gijsm/.rang-heavy.lock"
[ "${GRAM_HELD:-0}" = 1 ] && LOCK=""
{
    cat /proc/loadavg
    $LOCK bash -c '
        run="$0"; name="$1"; shift
        cat /proc/loadavg > "$run/load/$name.start"
        RAYON_NUM_THREADS="${GRAM_THREADS:-8}" perf stat -x, -e instructions,cycles \
            -o "$run/timing/$name.perf" \
            /usr/bin/time -v -o "$run/timing/$name.txt" "$@" 2>&1
        cat /proc/loadavg >> "$run/load/$name.start"
    ' "$RUN" "$NAME" "$BIN" "$ROOT/prep/$DATASET" "$RUN" "$NAME" "$MODE" "$@"
} | tee "$RUN/$NAME.log" | tail -n "${GRAM_TAIL:-4}"
sed -n 's/^\([0-9]*\),,\(instructions\|cycles\).*/\2 \1/p' "$RUN/timing/$NAME.perf" | tr '\n' ' '
echo
