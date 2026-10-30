#!/usr/bin/env bash
# Usage: bash tools/core-j-suite.sh outputs/core-j-<date>-NN
#
# Runs every core driver and comparator of research/core-j-packaging.md
# against its archive, through whichever backend RANG_CORE_BACKEND selects
# (ctypes or extension), writing each run into a subdirectory of the given
# fresh output directory and the wall time and peak RSS of every step into
# timings.tsv there. Exit status 1 when any step fails. Run from the checkout
# with .venv present and cargo on PATH.
set -uo pipefail
cd "$(dirname "$0")/.."
out=$1
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
py=.venv/bin/python
log=$out/timings.tsv
fail=0
printf 'step\tseconds\tmax_rss_kb\tstatus\n' > "$log"
run() {
  local name=$1; shift
  echo "## $name: $*"
  /usr/bin/time -o "$out/$name.time" -f '%e\t%M' "$@" > "$out/$name.log" 2>&1
  local status=$?
  printf '%s\t%s\t%s\n' "$name" "$(cat "$out/$name.time")" "$status" >> "$log"
  tail -3 "$out/$name.log"
  [ $status = 0 ] || { echo "FAILED: $name"; fail=1; }
}
echo "backend: ${RANG_CORE_BACKEND:-auto} RANG_CORE_LIB=${RANG_CORE_LIB:-}"
$py -c "from rang import core; print('backend', core.backend_name(), core.library_path())" 2>/dev/null || true

# Phase 2: the complex solver against QuartiCal's archived gains.
run phase2 $py examples/validate_core_phase2.py "$out/phase2"

# Section 6: the zarr-to-survey prototype and its checker.
run section6 $py examples/prototype_section6.py "$out/section6"
run section6-check $py examples/check_section6.py "$out/section6" \
  outputs/core-section6-oracle-20261029-01 \
  "$(awk '{printf "%.0f", $2 / 1024 + 0.5}' "$out/section6.time")" "$out/section6-check"

# Phase 3 actions stage.
run actions $py examples/run_core_campaign.py actions "$out/actions" \
  outputs/core-phase3-actions-inputs-20261029-01
run actions-compare $py examples/compare_core_actions.py "$out/actions/result.json" \
  research/results/gain-tv-actions.json "$out/actions/compare-archive.json"

# Task B: imaging weights and Stokes I against the WSClean oracle.
mkdir -p "$out/b"
ln -s "$(realpath outputs/core-b-20261030-01/oracle)" "$out/b/oracle"
run b $py examples/compare_core_weights.py "$out/b" --tolerance 4.76837158203125e-07

# Task C: the gridder on the fifteen archived jobs, pixels against the archive.
run c $py examples/run_core_gridder.py outputs/tv-next-imaging-wsl-20261029-01 \
  outputs/core-c-20261029-01 "$out/c"
run c-compare $py examples/compare_core_gridder.py \
  outputs/tv-next-imaging-wsl-20261029-01/images "$out/c/images" "$out/c/compare-archive.json"

# Task D: Tricolour strategies on the four archived controls.
run d $py examples/run_core_flags.py outputs/core-d-oracle-20261029-01/run \
  outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 "$out/d"
run d-compare $py examples/compare_core_flags.py run "$out/d" \
  outputs/tv-caracal-wsl-20261029-01 outputs/core-d-oracle-20261029-01/run "$out/d-compare"

# Task E: the Measurement Set reader against the python-casacore dump.
run e $py examples/check_ms_reader.py outputs/core-e-oracle-20261029-01 "$out/e"

# Task I: the imaging track replay (runs both of its comparators itself).
run i $py examples/run_core_imaging.py "$out/i"

echo "## overall: $([ $fail = 0 ] && echo PASS || echo FAIL)"
cat "$log"
exit $fail
