#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Case W on nash (research/multinode-executor.md, sections 3 and 4): the oracle
# O, then I, S1, S2, S4, S8 one after another, each under its own shared heavy
# lock ticket (2N+1 slots, 16+3N GB; O 4 slots, I 3), at nice 19 and ionice
# idle. Then the verdict and the report.
#
#   bash nash_points.sh RUN [ARM ...]
set -euo pipefail
source "$HOME/.rang-env.sh"
RUN=$1
shift
ARMS=("$@")
[ ${#ARMS[@]} -gt 0 ] || ARMS=(O I S1 S2 S4 S8)
HERE=$(cd "$(dirname "$0")" && pwd)
LOCK="$HOME/Github/rang/tools/heavy_lock.py"
PY=${RANG_MN_PYTHON:?}
mkdir -p "$RUN"
for arm in "${ARMS[@]}"; do
  case $arm in
    O) slots=4; mem=24 ;;
    I) slots=3; mem=16 ;;
    S*) n=${arm#S}; slots=$((2 * n + 1)); mem=$((16 + 3 * n)) ;;
  esac
  echo "== $(date -Is) $arm: queue $slots slots $mem GB"
  python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 "$PY" "$HERE/run.py" arm "$RUN" W "$arm"
  echo "== $(date -Is) $arm: done"
done
"$PY" "$HERE/run.py" verdict "$RUN" > "$RUN/verdict.log"
"$PY" "$HERE/run.py" report "$RUN" > "$RUN/report.log"
echo "== $(date -Is) all done"
