#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The whole W3 run (research/w3-chunking.md, section 3): every arm of section 2,
# the refusal of criterion 8 and the verdict.
# Usage: W3_ORACLE=<5ec40e3 checkout> bash tools/oracles/w3/all.sh RUN
# S and O are light; W and L take the heavy lock one arm at a time.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w3"
py="$root/.venv/bin/python"
run=$(realpath -m "$1")
mkdir -p "$run"
for case in S O; do
  for arm in U D T; do bash "$code/run.sh" "$run" "$case" "$arm"; done
done
for arm in U D T M; do
  flock "$HOME/.rang-heavy.lock" bash "$code/run.sh" "$run" W "$arm"
done
for arm in D M; do
  flock "$HOME/.rang-heavy.lock" bash "$code/run.sh" "$run" L "$arm"
done
# Criterion 8: one interval above a 2 GiB limit, refused before anything is written.
ref="$run/W-refusal"
mkdir -p "$ref/hashes" "$ref/logs"
flock "$HOME/.rang-heavy.lock" bash -c "
  cp -r /mnt/d/rang/outputs/w3/data/w3.ms '$ref/work.ms'
  '$py' '$code/compare.py' hashes '$ref/work.ms' '$ref/hashes/before.json'
  cat > '$ref/config.yaml' <<EOF
schema: rang-config
version: 1
fields: {fcal: [J1939-6342]}
data: {memory_limit_gb: 2}
calibrate:
  model: {source: setjy}
  primary: {terms: [{type: complex, solint: inf, freqint: inf}]}
EOF
  '$py' -m rang.core_cli calibrate '$ref/config.yaml' '$ref/work.ms' --run-dir '$ref/run' \
    > '$ref/logs/calibrate.log' 2>&1
  echo \"exit \$?\" > '$ref/logs/exit.txt'
  '$py' '$code/compare.py' hashes '$ref/work.ms' '$ref/hashes/after.json'
  ls -a '$ref' > '$ref/logs/listing.txt'
  rm -rf '$ref/work.ms' '$ref/work.ms.flagversions'
"
"$py" "$code/compare.py" verdict "$run" "$run/verdict.json" > "$run/verdict.log" 2>&1
echo "verdict: $run/verdict.json"
