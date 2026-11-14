#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The identity runs of research/chunk-task-api.md, section 2, one arm at a time
# under the heavy lock at normal priority, then the verdict.
#   RANG_CTA_ORACLE=~/Worktrees/rang/cta-oracle-30d9412 bash all.sh RUN [CASES]
set -u
run=$1
cases=${2:-"F O S C P W"}
here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../../.." && pwd)
py=${PY:-$HOME/Github/rang/.venv/Scripts/python.exe}
lock="python $HOME/Github/rang/tools/heavy_lock.py"
mkdir -p "$run"
git -C "$checkout" rev-parse HEAD > "$run/code-head.txt"
git -C "$checkout" status --short >> "$run/code-head.txt"
for case in $cases; do
  arms="U P1 P4 P2T"
  [ "$case" = W ] && arms="U P1 P4"
  for arm in $arms; do
    slots=4; mem=4
    [ "$arm" = P2T ] && slots=2
    if [ "$case" = W ]; then
      mem=20; [ "$arm" = P4 ] && mem=12
    fi
    start=$(date +%s)
    PYTHONPATH="$checkout/python" $lock run --slots $slots --mem $mem -- \
      "$py" "$here/run.py" arm "$run" "$case" "$arm"
    echo "$case-$arm: $(( $(date +%s) - start )) s including the queue"
  done
done
PYTHONPATH="$checkout/python" "$py" "$here/run.py" verdict "$run" > "$run/verdict.log"
tail -3 "$run/verdict.log"
