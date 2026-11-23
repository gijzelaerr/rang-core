#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The identity runs of research/chunk-task-api-1b.md, section 2, one arm at a
# time under the heavy lock at normal priority, then the verdict.
#   RANG_CTA_ORACLE=~/Worktrees/rang/cta1b-oracle-e071bdab bash all_1b.sh RUN [CASES]
set -u
run=$1
cases=${2:-"C P M W"}
here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../../.." && pwd)
py=${PY:-$checkout/.venv/Scripts/python.exe}
lock="python $HOME/Github/rang/tools/heavy_lock.py"
mkdir -p "$run"
[ -e "$run/owner.txt" ] && { echo "$run is owned: $(cat "$run/owner.txt")"; exit 3; }
echo "pid $$ $(date -u +%FT%TZ)" > "$run/owner.txt"
git -C "$checkout" rev-parse HEAD > "$run/code-head.txt"
git -C "$checkout" status --short >> "$run/code-head.txt"
for case in $cases; do
  arms="U P1 P4 P2T"
  [ "$case" = W ] && arms="U P1 P4"
  for arm in $arms; do
    slots=4; mem=4
    [ "$arm" = P2T ] && slots=2
    if [ "$case" = W ]; then
      mem=24  # amendment 2: memory_limit_gb 20 in every W arm
    fi
    start=$(date +%s)
    $lock run --slots $slots --mem $mem -- "$py" "$here/run_1b.py" arm "$run" "$case" "$arm"
    echo "$case-$arm: $(( $(date +%s) - start )) s including the queue"
  done
done
"$py" "$here/run_1b.py" verdict "$run" > "$run/verdict.log" 2>&1
tail -3 "$run/verdict.log"
