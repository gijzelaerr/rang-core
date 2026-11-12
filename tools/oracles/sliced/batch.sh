#!/usr/bin/env bash
# The arms all.sh has not finished, back to back inside ONE heavy-lock hold
# (coordinator's request 2026-11-12: a separate exclusive ticket per arm
# drains the shared jobs before each one and leaves the host idle). Run it
# under the lock once, exclusive:
#   heavy_lock.py run -- "C:/Program Files/Git/bin/bash.exe" tools/oracles/sliced/batch.sh RUN BASE
# (Git Bash by its path: a bare `bash` from Python is WSL's bash.exe)
# Each arm still records `heavy_lock.py status` at its start
# (logs/lock-status.txt). Finished arms are skipped, so the order and the
# arms are all.sh's.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
run=$1; base=$2
py="$root/.venv/Scripts/python.exe"
harness="$root/tools/oracles/sliced/run.py"
one() {  # case arm [base]
  local case=$1 arm=$2 code=${3:-}
  local name="$case-$arm"
  [ -n "$code" ] && [ "$arm" != U ] && name="$case-B$arm"
  if [ -e "$run/$name/logs/calibrate.exit" ]; then echo "$name done"; return; fi
  rm -rf "$run/$name"
  local extra=()
  [ -n "$code" ] && extra=(--base "$code")
  "$py" "$harness" "$run" "$case" "$arm" "${extra[@]}"
}
for c in O C P; do one $c U "$base"; done
for a in D T M; do one O $a; done
for a in D M; do one C $a; done
one P M
for c in C P; do one $c T "$base"; one $c T; done
one P D "$base"; one P D
one W D "$base"; one W D
one W M "$base"; one W M
"$py" "$harness" verdict "$run" "$run/verdict-1-2.json"
one H U "$base"
for a in D M; do one H $a; done
one H T "$base"; one H T
"$py" "$harness" verdict "$run" "$run/verdict.json"
