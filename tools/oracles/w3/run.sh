#!/usr/bin/env bash
# W3 arms (research/w3-chunking.md, sections 2 and 3).
# Usage: bash tools/oracles/w3/run.sh RUN CASE ARM
#   CASE: S (A1 small), O (O-CASA slice), W (the whole-array set), L (A1 full, read only)
#   ARM:  U (main 5ec40e3, unchunked; needs $W3_ORACLE, a checkout of 5ec40e3 with
#         this branch's extension copied in), D (default limit), T (tiny chunks),
#         M (memory_limit_gb 2)
# Each arm runs on a fresh copy of the MS (L: on the frozen MS, calibrate only), records
# /usr/bin/time -v per stage and casacure hashes after each stage. W's copy is removed
# after the arm (disk); its hashes, run directory and timings stay.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w3"
py="$root/.venv/bin/python"
run=$(realpath -m "$1"); case=$2; arm=$3
strategy=$HOME/Github/rang/outputs/caracal-strategy-inputs-8f7bb363/mk_rfi_flagging_calibrator_fields_firstpass.yaml
case $case in
  S) src=/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms ;;
  O) src=$HOME/Github/rang/outputs/o-casa-20261030-01/work.ms ;;
  W) src=/mnt/d/rang/outputs/w3/data/w3.ms ;;
  L) src=/mnt/d/rang/outputs/fp-a1-20261106-simtruth/full/a1-full.ms ;;
  *) echo "unknown case $case" >&2; exit 1 ;;
esac
dir="$run/$case-$arm"
if [ -e "$dir" ]; then echo "$dir exists; choose a fresh run" >&2; exit 1; fi
mkdir -p "$dir/timing" "$dir/logs" "$dir/hashes"
cp "$strategy" "$dir/strategy.yaml"
env=()
if [ "$arm" = U ]; then
  : "${W3_ORACLE:?set W3_ORACLE to the 5ec40e3 checkout}"
  env=(env "PYTHONPATH=$W3_ORACLE/python")
fi
"${env[@]}" "$py" -c "import rang, sys; print(rang.__file__)" > "$dir/logs/rang-path.txt"
if [ "$case" = L ]; then
  ms=$src
  stages=(calibrate)
else
  ms="$dir/work.ms"
  cp -r "$src" "$ms"
  stages=(flag calibrate apply)
fi
nrows=$("$py" -c "from rang import core_ms; t = core_ms.open_table('$ms'); print(t.nrows); t.close()")
"$py" "$code/compare.py" config "$case" "$arm" "$nrows" "$dir/config.yaml" "$dir/strategy.yaml"
if [ "$case" != L ]; then
  "$py" "$code/compare.py" hashes "$ms" "$dir/hashes/pristine.json"
fi
for stage in "${stages[@]}"; do
  /usr/bin/time -v -o "$dir/timing/$stage.txt" "${env[@]}" "$py" -m rang.core_cli \
    "$stage" "$dir/config.yaml" "$ms" --run-dir "$dir/run" > "$dir/logs/$stage.log" 2>&1
  status=$?
  echo "$case-$arm $stage exit $status $(grep -E 'Maximum resident' "$dir/timing/$stage.txt" | awk '{print $NF}') KB $(grep -E 'Elapsed' "$dir/timing/$stage.txt" | awk '{print $NF}')"
  if [ "$case" != L ]; then
    "$py" "$code/compare.py" hashes "$ms" "$dir/hashes/$stage.json"
  fi
  [ $status -eq 0 ] || break
done
if [ "$case" = W ]; then
  du -sb "$ms" "$ms.flagversions" > "$dir/logs/disk.txt" 2>&1
  rm -rf "$ms" "$ms.flagversions"
fi
