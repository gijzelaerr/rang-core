#!/usr/bin/env bash
# W3b arms (research/w3b-chainchunks.md, sections 2 and 3).
# Usage: bash tools/oracles/w3b/run.sh RUN CASE ARM
#   CASE: O (O-CASA slice), C (A1 small, C2e chain), P (poldx), H (polholdout, held out),
#         W (the whole-array set, K G B; calibrate only)
#   ARM:  U (main ba65792 unchunked; needs $W3B_ORACLE, a checkout of ba65792 with its own
#         extension), D (default limit), T (chunk_rows 7), M (the frozen low limit),
#         R (W only: K solint inf at the default limit, refused before anything is written)
# Each arm runs on a fresh copy named work.ms, records /usr/bin/time -v per stage and
# casacure hashes before and after each stage. W's copy is removed after the arm (disk).
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w3b"
py="$root/.venv/bin/python"
run=$(realpath -m "$1"); case=$2; arm=$3
src=$("$py" -c "import sys; sys.path.insert(0, '$code'); import compare; print(compare.SOURCES['$case'])")
dir="$run/$case-$arm"
if [ -e "$dir" ]; then echo "$dir exists; choose a fresh run" >&2; exit 1; fi
mkdir -p "$dir/timing" "$dir/logs" "$dir/hashes"
env=()
if [ "$arm" = U ]; then
  : "${W3B_ORACLE:?set W3B_ORACLE to the ba65792 checkout}"
  env=(env "PYTHONPATH=$W3B_ORACLE/python")
fi
"${env[@]}" "$py" -c "import rang, rang._core; print(rang.__file__, rang._core.__file__)" > "$dir/logs/rang-path.txt"
ms="$dir/work.ms"
cp -r "$src" "$ms"
"$py" "$code/compare.py" config "$case" "$arm" "$ms" "$dir/config.yaml"
"$py" "$code/compare.py" hashes "$ms" "$dir/hashes/pristine.json"
if [ "$case" = W ]; then stages=(calibrate); else stages=(calibrate apply); fi
for stage in "${stages[@]}"; do
  /usr/bin/time -v -o "$dir/timing/$stage.txt" "${env[@]}" "$py" -m rang.core_cli \
    "$stage" "$dir/config.yaml" "$ms" --run-dir "$dir/run" > "$dir/logs/$stage.log" 2>&1
  status=$?
  echo "$status" > "$dir/logs/$stage.exit"
  echo "$case-$arm $stage exit $status $(grep -E 'Maximum resident' "$dir/timing/$stage.txt" | awk '{print $NF}') KB $(grep -E 'Elapsed' "$dir/timing/$stage.txt" | awk '{print $NF}')"
  if [ "$arm" = R ]; then
    "$py" "$code/compare.py" hashes "$ms" "$dir/hashes/after-refusal.json"
    ls -a "$dir" "$ms" > "$dir/logs/listing.txt"
    break
  fi
  "$py" "$code/compare.py" hashes "$ms" "$dir/hashes/$stage.json"
  [ $status -eq 0 ] || break
done
du -sb "$ms" > "$dir/logs/disk.txt" 2>&1
if [ "$case" = W ]; then
  rm -rf "$ms" "$ms.flagversions"
fi
