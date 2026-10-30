#!/usr/bin/env bash
# S1 timed suite: every archived chain under /usr/bin/time, no profiler.
# Usage: bash suite.sh outputs/simplification-review-20261030-NN [steps...]
set -uo pipefail
cd ~/Worktrees/rang/simplification-review
export PATH=$HOME/.cargo/bin:$PATH
export RUSTUP_TOOLCHAIN=1.93
out=$1; shift
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
py=.venv/bin/python
log=$out/timings.tsv
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/s1
printf 'step\twall_s\tuser_s\tsys_s\tmax_rss_kb\tcpu_pct\tstatus\tload_before\tload_after\n' > "$log"
want() { [ $# -eq 0 ] && return 0; return 1; }
STEPS=" $* "
run() {
  local name=$1; shift
  if [ "$STEPS" != "  " ] && [[ "$STEPS" != *" $name "* ]]; then return; fi
  echo "## $name: $*"
  local lb; lb=$(cut -d' ' -f1-3 /proc/loadavg)
  /usr/bin/time -o "$out/$name.time" -f '%e\t%U\t%S\t%M\t%P' "$@" > "$out/$name.log" 2>&1
  local status=$?
  local la; la=$(cut -d' ' -f1-3 /proc/loadavg)
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$(tail -1 "$out/$name.time")" "$status" "$lb" "$la" >> "$log"
  tail -2 "$out/$name.log"
}
run precondition $py examples/precondition_luno_campaign.py "$out/precondition"
run precondition-blas1 env OPENBLAS_NUM_THREADS=1 $py examples/precondition_luno_campaign.py "$out/precondition-blas1"
run kcheck $py examples/check_luno_campaign.py outputs/core-k-20261030-01 outputs/core-k-20261030-00-precondition "$out/kcheck"
run campaign $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign" --images original,tricolour-firstpass,tricolour-mild
run campaign-blas1 env OPENBLAS_NUM_THREADS=1 $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign-blas1" --images original
run section6 $py examples/prototype_section6.py "$out/section6"
run section6-blas1 env OPENBLAS_NUM_THREADS=1 $py examples/prototype_section6.py "$out/section6-blas1"
run section6-check $py examples/check_section6.py "$out/section6" outputs/core-section6-oracle-20261029-01 200 "$out/section6-check"
run phase2 $py examples/validate_core_phase2.py "$out/phase2"
run bench-f $py examples/bench_core_f.py check "$out/bench-f" outputs/core-f-20261029-01/baseline.json
run actions $py -m rangtoy.core_cli actions "$out/actions" outputs/core-phase3-actions-inputs-20261029-01
run actions-compare $py -m rangtoy.core_cli compare actions "$out/actions/result.json" research/results/gain-tv-actions.json "$out/actions-compare.json"
run injections $py -m rangtoy.core_cli injections "$out/injections" outputs/tv-injections-wsl-20261029-01
run injections-compare $py -m rangtoy.core_cli compare injections "$out/injections/result.json" research/results/gain-tv-injections.json "$out/injections-compare.json"
run prospective $py -m rangtoy.core_cli prospective "$out/prospective" outputs/tv-next-wsl-20261029-01/inputs
run prospective-compare $py -m rangtoy.core_cli compare prospective "$out/prospective/result.json" research/results/gain-tv-next-prospective.json "$out/prospective-compare.json"
run signal $py -m rangtoy.core_cli signal "$out/signal" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01
run signal-compare $py -m rangtoy.core_cli compare signal "$out/signal/result.json" research/results/gain-tv-next-signal.json "$out/signal-compare.json"
run trend-mirror $py -m rangtoy.core_cli trend-mirror "$out/trend-mirror" outputs/tv-concurrent-wsl-20261029-01
run trend $py -m rangtoy.core_cli trend "$out/trend" "$out/trend-mirror"
run trend-blas1 env OPENBLAS_NUM_THREADS=1 $py -m rangtoy.core_cli trend "$out/trend-blas1" "$out/trend-mirror"
run trend-compare $py -m rangtoy.core_cli compare trend "$out/trend/result.json" research/results/gain-tv-next-trend.json "$out/trend-compare.json" --posthoc-slope-scale
mkdir -p "$out/b"; ln -sfn "$(realpath outputs/core-b-20261030-01/oracle)" "$out/b/oracle"
run b $py examples/compare_core_weights.py "$out/b" --tolerance 4.76837158203125e-07
run c $py examples/run_core_gridder.py outputs/tv-next-imaging-wsl-20261029-01 outputs/core-c-20261029-01 "$out/c"
run c-compare $py examples/compare_core_gridder.py outputs/tv-next-imaging-wsl-20261029-01/images "$out/c/images" "$out/c/compare-archive.json"
run d $py examples/run_core_flags.py outputs/core-d-oracle-20261029-01/run outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 "$out/d"
run d-compare $py examples/compare_core_flags.py run "$out/d" outputs/tv-caracal-wsl-20261029-01 outputs/core-d-oracle-20261029-01/run "$out/d-compare"
run e $py examples/check_ms_reader.py outputs/core-e-oracle-20261029-01 "$out/e"
run i $py examples/run_core_imaging.py "$out/i"
echo "## done"
cat "$log"
