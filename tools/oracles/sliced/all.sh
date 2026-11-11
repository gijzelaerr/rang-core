#!/usr/bin/env bash
# The sliced-read runs (research/sliced-read.md, sections 2 to 4), in order:
# correctness arms as shared heavy-lock jobs, timing arms exclusive, the
# held-out H last. Usage (Git Bash on Windows):
#   bash tools/oracles/sliced/all.sh RUN BASE
# RUN a fresh directory under D:\rang\outputs, BASE the bd15126 checkout with
# its own extension. Finished arms are kept (a rerun skips them).
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
run=$1; base=$2
py="$root/.venv/Scripts/python.exe"
lock="$HOME/Github/rang/.venv/Scripts/python.exe $HOME/Github/rang/tools/heavy_lock.py"
harness="$root/tools/oracles/sliced/run.py"
mkdir -p "$run"
one() {  # mode case arm [base]
  local mode=$1 case=$2 arm=$3 code=${4:-}
  local name="$case-$arm"
  [ -n "$code" ] && [ "$arm" != U ] && name="$case-B$arm"
  if [ -e "$run/$name/logs/calibrate.exit" ]; then echo "$name done"; return; fi
  rm -rf "$run/$name"
  local extra=()
  [ -n "$code" ] && extra=(--base "$code")
  if [ "$mode" = shared ]; then
    $lock run --slots 8 --mem 16 -- "$py" "$harness" "$run" "$case" "$arm" "${extra[@]}"
  else
    $lock run -- "$py" "$harness" "$run" "$case" "$arm" "${extra[@]}"
  fi
}
# 1. Correctness, shared.
for c in O C P; do one shared $c U "$base"; done
for a in D T M; do one shared O $a; done
for a in D M; do one shared C $a; done
one shared P M
# 2. Timing, exclusive: before (base) and after (branch), same arm.
for c in C P; do one exclusive $c T "$base"; one exclusive $c T; done
one exclusive P D "$base"; one exclusive P D
one exclusive W D "$base"; one exclusive W D
one exclusive W M "$base"; one exclusive W M
"$py" "$harness" verdict "$run" "$run/verdict-1-2.json"
# 3. Held out, after 1 and 2.
one shared H U "$base"
for a in D M; do one shared H $a; done
one exclusive H T "$base"; one exclusive H T
"$py" "$harness" verdict "$run" "$run/verdict.json"
