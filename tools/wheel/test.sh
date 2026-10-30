#!/usr/bin/env bash
# Usage: bash tools/wheel/test.sh BUILD_DIR outputs/OUT_DIR [PYTHON_VERSION ...]
# (both paths relative to the checkout)
#
# Tests the wheel in BUILD_DIR/dist (from tools/wheel/build.sh) on clean
# uv-managed CPython interpreters (default 3.10 3.11 3.12 3.13 3.14), as in
# research/wheel.md. Per version, in OUT_DIR/py<version>/:
#   bare     fresh venv, `uv pip install <wheel>` alone, then
#            `import rangtoy._core` and `import rangtoy.core` with cargo absent
#   extras   install the wheel with its test and imaging extras
#   nocargo  with cargo absent from PATH (env -i, outside the checkout): the
#            backend is the extension from site-packages and a fused pass runs
#   pytest   tests/test_core_backends.py from the source tree against the
#            installed wheel (tools/wheel/pytest_wheel.py), cargo absent;
#            any skip other than the fixture-MS one fails the step
#   suite    when SUITE=1 (default for 3.10 and 3.14, SUITE_ALL=1 for every
#            version): the drivers of tools/core-j-suite.sh through
#            tools/wheel/run_installed.py, cargo absent, then
#            examples/compare_core_backends.py against the task J extension
#            run outputs/core-j-20261029-02-extension (recorded, not gated:
#            it always differs in run-path strings), and
#            tools/wheel/classify_compare.py on its receipt (gated)
# Wall times go to OUT_DIR/timings.tsv. Exit status 1 when a gated step
# fails; note that the section 6 checker's cost criterion (2.0 s) fails on a
# loaded host, which fails its step (research/wheel.md).
# Archives are only read; every run writes into OUT_DIR, which must be fresh.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
src=$(pwd -P)
build=$(cd "$1" && pwd -P)
out=$2
# The drivers accept only run directories given as relative outputs/ paths.
rel=$2
case $rel in outputs/*) ;; *) echo "OUT_DIR must be outputs/... (relative to the checkout)"; exit 2;; esac
shift 2
versions=("$@")
[ ${#versions[@]} = 0 ] && versions=(3.10 3.11 3.12 3.13 3.14)
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
out=$(cd "$out" && pwd -P)
wheel=$(ls "$build"/dist/*.whl)
ctypes_lib=$build/ctypes/librang_core.so
reference=${REFERENCE:-$src/outputs/core-j-20261029-02-extension}
export UV_INDEX_URL=https://pypi.org/simple
log=$out/timings.tsv
printf 'python\tstep\tseconds\tmax_rss_kb\tstatus\n' > "$log"
fail=0
# A clean environment without cargo: no login profile, no ~/.cargo/bin.
clean=(env -i HOME="$HOME" PATH=/usr/bin:/bin LANG=C.UTF-8)

run() {
  local version=$1 name=$2; shift 2
  local dir=$out/py$version
  echo "## $version $name"
  /usr/bin/time -o "$dir/$name.time" -f '%e\t%M' "$@" > "$dir/$name.log" 2>&1
  local status=$?
  printf '%s\t%s\t%s\t%s\n' "$version" "$name" "$(cat "$dir/$name.time")" "$status" >> "$log"
  tail -n 3 "$dir/$name.log"
  [ $status = 0 ] || [ "${UNGATED:-0}" = 1 ] || { echo "FAILED: $version $name"; fail=1; }
  return $status
}

for version in "${versions[@]}"; do
  dir=$out/py$version
  mkdir -p "$dir"
  bare=$dir/venv-bare
  venv=$dir/venv
  uv venv -q --python-preference only-managed -p "$version" "$bare"
  uv venv -q --python-preference only-managed -p "$version" "$venv"
  "$venv/bin/python" -VV > "$dir/python.txt"
  run "$version" bare-install uv pip install --python "$bare/bin/python" "$wheel"
  run "$version" bare-import "${clean[@]}" "$bare/bin/python" -I -c \
    "import rangtoy._core, rangtoy.core as c; print(c.backend_name(), c.library_path())"
  run "$version" install uv pip install --python "$venv/bin/python" "${wheel}[test,imaging]"
  uv pip freeze --python "$venv/bin/python" > "$dir/freeze.txt"
  run "$version" nocargo "${clean[@]}" bash -c "cd '$dir' && ! command -v cargo && \
    '$venv/bin/python' -I '$src/tools/wheel/smoke.py'"
  run "$version" pytest "${clean[@]}" PYTHONPATH="$src/tools/wheel" \
    RANG_WHEEL_CTYPES_LIB="$ctypes_lib" bash -c "set -o pipefail; cd '$src' && ! command -v cargo && \
    '$venv/bin/python' -m pytest -p pytest_wheel -p no:cacheprovider -o pythonpath= \
    -rs -q tests/test_core_backends.py | tee '$dir/pytest.out' && \
    ! grep -E '^SKIPPED' '$dir/pytest.out' | grep -v 'fixture MS not present'"
  if [ "${SUITE_ALL:-0}" = 1 ] || { [ "${SUITE:-1}" = 1 ] && { [ "$version" = 3.10 ] || [ "$version" = 3.14 ]; }; }; then
    suite=$rel/py$version/suite
    mkdir -p "$suite"
    py=("${clean[@]}" "$venv/bin/python" "$src/tools/wheel/run_installed.py")
    # actions, D and I need files the wheel does not carry (checkout-relative
    # ROOT constants, core/data static masks): run_installed.py points those
    # names at the checkout; the code and kernels are still the wheel's.
    shim=("${clean[@]}" RANG_WHEEL_CHECKOUT="$src" "$venv/bin/python" \
      "$src/tools/wheel/run_installed.py")
    # Phase 2, section 6 and actions call the root crate's TV kernel (rangtoy.projector),
    # which the wheel does not ship: RANG_TOY_LIB names the container build.
    toy=("${clean[@]}" RANG_TOY_LIB="$build/ctypes/librang_toy.so")
    # The section 6 prototype calls core.library() (the ctypes handle) before
    # timing even under the extension; RANG_CORE_BACKEND=extension keeps the
    # extension active while RANG_CORE_LIB lets that call load the wheel's
    # own binary, which exports the C ABI (research/core-j-packaging.md).
    ext_so=$(echo "$venv"/lib/python*/site-packages/rangtoy/_core.abi3.so)
    s6=("${toy[@]}" RANG_CORE_BACKEND=extension RANG_CORE_LIB="$ext_so" \
      "$venv/bin/python" "$src/tools/wheel/run_installed.py")
    run "$version" phase2 "${toy[@]}" "$venv/bin/python" "$src/tools/wheel/run_installed.py" \
      examples/validate_core_phase2.py "$suite/phase2"
    run "$version" section6 "${s6[@]}" examples/prototype_section6.py "$suite/section6"
    run "$version" section6-check "${s6[@]}" examples/check_section6.py "$suite/section6" \
      outputs/core-section6-oracle-20261029-01 \
      "$(awk '{printf "%.0f", $2 / 1024 + 0.5}' "$dir/section6.time")" "$suite/section6-check"
    run "$version" actions "${toy[@]}" RANG_WHEEL_CHECKOUT="$src" "$venv/bin/python" \
      "$src/tools/wheel/run_installed.py" examples/run_core_campaign.py actions "$suite/actions" \
      outputs/core-phase3-actions-inputs-20261029-01
    run "$version" actions-compare "${py[@]}" examples/compare_core_actions.py \
      "$suite/actions/result.json" research/results/gain-tv-actions.json \
      "$suite/actions/compare-archive.json"
    mkdir -p "$suite/b"
    ln -s "$(realpath outputs/core-b-20261030-01/oracle)" "$suite/b/oracle"
    run "$version" b "${py[@]}" examples/compare_core_weights.py "$suite/b" \
      --tolerance 4.76837158203125e-07
    run "$version" c "${py[@]}" examples/run_core_gridder.py \
      outputs/tv-next-imaging-wsl-20261029-01 outputs/core-c-20261029-01 "$suite/c"
    run "$version" c-compare "${py[@]}" examples/compare_core_gridder.py \
      outputs/tv-next-imaging-wsl-20261029-01/images "$suite/c/images" \
      "$suite/c/compare-archive.json"
    run "$version" d "${shim[@]}" examples/run_core_flags.py outputs/core-d-oracle-20261029-01/run \
      outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 "$suite/d"
    run "$version" d-compare "${py[@]}" examples/compare_core_flags.py run "$suite/d" \
      outputs/tv-caracal-wsl-20261029-01 outputs/core-d-oracle-20261029-01/run "$suite/d-compare"
    run "$version" e "${py[@]}" examples/check_ms_reader.py outputs/core-e-oracle-20261029-01 \
      "$suite/e"
    run "$version" i "${shim[@]}" examples/run_core_imaging.py "$suite/i" \
      outputs/tv-next-imaging-wsl-20261029-01 outputs/core-c-20261029-01/inputs
    # File by file against task J's extension run; section6-warm and its check
    # exist only there (a labelled repeat), so they are ignored. The raw
    # comparator always fails here, on run-path strings (task J used
    # checkout-absolute paths in another worktree), so its status is recorded
    # but not gated; classify_compare.py is the gate: it fails on missing
    # files or unexplained differences and reports float differences.
    UNGATED=1 run "$version" compare "${clean[@]}" "$venv/bin/python" \
      examples/compare_core_backends.py "$reference" "$suite" "$dir/compare-backends.json" \
      "section6-warm,section6-warm-check,${IGNORE:-}"
    run "$version" classify "${clean[@]}" "$venv/bin/python" -I "$src/tools/wheel/classify_compare.py" \
      "$dir/compare-backends.json" "$dir/compare-classes.json"
  fi
done
echo "## overall: $([ $fail = 0 ] && echo PASS || echo FAIL)"
column -t -s $'\t' "$log"
exit $fail
