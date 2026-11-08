#!/usr/bin/env bash
# The W3b run (research/w3b-chainchunks.md, section 3): O, C and P against U, W's D and M
# and the refusal, then the verdict. The held-out case H runs separately, after this.
# Usage: W3B_ORACLE=<ba65792 checkout> bash tools/oracles/w3b/all.sh RUN
# Arms already in RUN are kept (a restarted run continues). O, C and P arms (under
# 0.3 GiB, no timing claim) run without the heavy lock; each W arm takes it.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w3b"
py="$root/.venv/bin/python"
run=$(realpath -m "$1")
mkdir -p "$run"
for case in O C P; do
  for arm in U D T M; do
    [ -e "$run/$case-$arm" ] && continue
    bash "$code/run.sh" "$run" "$case" "$arm"
  done
done
for arm in D M R; do
  [ -e "$run/W-$arm" ] && continue
  flock "$HOME/.rang-heavy.lock" bash "$code/run.sh" "$run" W "$arm"
done
"$py" "$code/compare.py" verdict "$run" "$run/verdict.json" > "$run/verdict.log" 2>&1
echo "verdict: $run/verdict.json"
