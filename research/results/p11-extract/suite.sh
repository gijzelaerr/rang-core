#!/usr/bin/env bash
# P11 live-chain suite (research/p11-extract.md): S1's suite
# (research/results/profiles-20261030/scripts/suite.sh) through `rang-core
# STAGE VERB`, every step under coverage (sys.monitoring) with
# --source=python/rangtoy,history so that "no history/ module executed" is measured.
# K replay and K checker are dropped: outputs/core-k-20261030-01/fetch was pruned
# (research/p9-cli.md). L1 and L2 preconditions are added (core_campaign_array,
# core_campaign_1830).
# Usage: bash suite.sh outputs/p11-20261030-NN [steps...]
set -uo pipefail
cd ~/Worktrees/rang/p11-retire
export PATH=$HOME/.cargo/bin:$PATH
export OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4 COVERAGE_CORE=sysmon
out=$1; shift
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
export COVERAGE_FILE=$PWD/$out/.coverage
py=.venv/bin/python
cov="$py -m coverage run -p --source=python/rangtoy,history"
log=$out/timings.tsv
printf 'step\twall_s\tuser_s\tsys_s\tmax_rss_kb\tcpu_pct\tstatus\tload_before\tload_after\n' > "$log"
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
rc="$cov -m rangtoy.core_cli"
run precondition $rc campaign precondition "$out/precondition"
run l1-precondition $rc campaign-array precondition "$out/l1-precondition"
run l2-precondition $rc campaign-1830 precondition "$out/l2-precondition"
run section6 $rc section6 run "$out/section6"
run section6-check $rc section6 compare "$out/section6" outputs/core-section6-oracle-20261029-01 200 "$out/section6-check"
run phase1 $cov examples/validate_core_phase1.py "$out/phase1"
run phase2 $cov examples/validate_core_phase2.py "$out/phase2"
run phase3c-a $cov examples/validate_core_phase3c_a.py outputs/core-phase3c-oracle-20261029-01 "$out/phase3c-a"
run bench-f $rc bench f check "$out/bench-f" outputs/core-f-20261029-01/baseline.json
run actions $rc actions run "$out/actions" outputs/core-phase3-actions-inputs-20261029-01
run actions-compare $rc actions compare "$out/actions/result.json" research/results/gain-tv-actions.json "$out/actions-compare.json"
run injections $rc injections run "$out/injections" outputs/tv-injections-wsl-20261029-01
run injections-compare $rc injections compare "$out/injections/result.json" research/results/gain-tv-injections.json "$out/injections-compare.json"
run prospective $rc prospective run "$out/prospective" outputs/tv-next-wsl-20261029-01/inputs
run prospective-compare $rc prospective compare "$out/prospective/result.json" research/results/gain-tv-next-prospective.json "$out/prospective-compare.json"
run signal $rc signal run "$out/signal" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01
run signal-compare $rc signal compare "$out/signal/result.json" research/results/gain-tv-next-signal.json "$out/signal-compare.json"
run signal-p6 env RANG_P6=1 $rc signal run "$out/signal-p6" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01
run signal-p6-compare $rc signal compare "$out/signal-p6/result.json" research/results/gain-tv-next-signal.json "$out/signal-p6-compare.json"
run trend-mirror $rc trend mirror "$out/trend-mirror" outputs/tv-concurrent-wsl-20261029-01
run trend $rc trend run "$out/trend" "$out/trend-mirror"
run trend-compare $rc trend compare "$out/trend/result.json" research/results/gain-tv-next-trend.json "$out/trend-compare.json"
run trend-compare-posthoc $rc trend compare "$out/trend/result.json" research/results/gain-tv-next-trend.json "$out/trend-compare-posthoc.json" --posthoc-slope-scale
mkdir -p "$out/b"; ln -sfn "$(realpath outputs/core-b-20261030-01/oracle)" "$out/b/oracle"
run b $rc weights compare "$out/b" --tolerance 4.76837158203125e-07
run c $rc gridder run outputs/tv-next-imaging-wsl-20261029-01 outputs/core-c-20261029-01 "$out/c"
run c-compare $rc gridder compare outputs/tv-next-imaging-wsl-20261029-01/images "$out/c/images" "$out/c/compare-archive.json"
run d $rc flags run outputs/core-d-oracle-20261029-01/run outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 "$out/d"
run d-compare $rc flags compare run "$out/d" outputs/tv-caracal-wsl-20261029-01 outputs/core-d-oracle-20261029-01/run "$out/d-compare"
run e $rc ms compare outputs/core-e-oracle-20261029-01 "$out/e"
run i $rc imaging replay "$out/i"
run i-compare $rc imaging compare "$out/i/result.json" research/results/gain-tv-next-imaging.json "$out/i-compare.json" --images "$out/i/images" outputs/tv-next-imaging-wsl-20261029-01/images
run i-compare-host $rc imaging compare "$out/i/result.json" outputs/tv-next-imaging-wsl-20261029-01/result.json "$out/i-compare-host.json"
echo "## done"
cat "$log"
$py -m coverage combine "$out" > /dev/null 2>&1
$py -m coverage json -o "$out/coverage.json" > /dev/null 2>&1
$py -m coverage report > "$out/coverage-report.txt" 2>&1
