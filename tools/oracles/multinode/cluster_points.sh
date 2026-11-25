#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The container-cluster arms of research/multinode-2.md on nash, one after
# another, each under its own shared heavy-lock ticket sized to the cluster's
# container caps (cluster_arms.booking), at nice 19 and ionice idle; then the
# verdict and the report.
#
#   bash cluster_points.sh RUN CASE ARM [ARM ...]
#
# Needs: RANG_MN_SHARED (RUN inside it), RANG_MN_MOUNTS, RANG_MN_F, RANG_MN_W,
# RANG_MN_STRATEGY, RANG_MN_ORACLE, RANG_MN_PYTHON (see run.py).
set -euo pipefail
source "$HOME/.rang-env.sh"
RUN=$1
CASE=$2
shift 2
HERE=$(cd "$(dirname "$0")" && pwd)
LOCK="$HOME/Github/rang/tools/heavy_lock.py"
PY=${RANG_MN_PYTHON:?}
export RANG_MN_CLUSTER=1
mkdir -p "$RUN"
for arm in "$@"; do
  read -r slots mem < <(cd "$HERE" && "$PY" -c "
import cluster_arms as c
s, g = c.booking(c.spec('$CASE', '$arm'), None)
print(s, g)")
  echo "== $(date -Is) $CASE-$arm: queue $slots slots $mem GB"
  python3 "$LOCK" run --slots "$slots" --mem "$mem" -- \
    nice -n 19 ionice -c3 "$PY" "$HERE/run.py" arm "$RUN" "$CASE" "$arm"
  echo "== $(date -Is) $CASE-$arm: done"
done
"$PY" "$HERE/run.py" verdict "$RUN" > "$RUN/verdict.log"
"$PY" "$HERE/run.py" report "$RUN" > "$RUN/report.log" || true
echo "== $(date -Is) all done"
