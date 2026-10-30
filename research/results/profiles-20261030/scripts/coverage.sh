#!/usr/bin/env bash
# S1: which lines of python/rangtoy the live core chains execute.
# Usage: bash coverage.sh outputs/simplification-review-20261030-NN
set -uo pipefail
cd ~/Worktrees/rang/simplification-review
export PATH=$HOME/.cargo/bin:$PATH
export RUSTUP_TOOLCHAIN=1.93 OPENBLAS_NUM_THREADS=1 COVERAGE_CORE=sysmon
out=$1
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
py=.venv/bin/python
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/s1
export COVERAGE_FILE=$out/.coverage
cov() { local name=$1; shift; echo "## $name"; /usr/bin/time -f "$name %e s %M KB" $py -m coverage run -p --source=python/rangtoy "$@" > "$out/$name.log" 2>&1; tail -1 "$out/$name.log"; }
cov campaign $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign" --images original
cov precondition examples/precondition_luno_campaign.py "$out/precondition"
cov kcheck examples/check_luno_campaign.py outputs/core-k-20261030-01 outputs/core-k-20261030-00-precondition "$out/kcheck"
cov section6 examples/prototype_section6.py "$out/section6"
cov actions -m rangtoy.core_cli actions "$out/actions" outputs/core-phase3-actions-inputs-20261029-01
cov injections -m rangtoy.core_cli injections "$out/injections" outputs/tv-injections-wsl-20261029-01
cov prospective -m rangtoy.core_cli prospective "$out/prospective" outputs/tv-next-wsl-20261029-01/inputs
cov signal -m rangtoy.core_cli signal "$out/signal" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01
cov trend-mirror -m rangtoy.core_cli trend-mirror "$out/trend-mirror" outputs/tv-concurrent-wsl-20261029-01
cov trend -m rangtoy.core_cli trend "$out/trend" "$out/trend-mirror"
cov imaging examples/run_core_imaging.py "$out/imaging"
cov flags examples/run_core_flags.py outputs/core-d-oracle-20261029-01/run outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 "$out/d"
$py -m coverage combine "$out" > /dev/null 2>&1 || $py -m coverage combine
$py -m coverage json -o "$out/coverage.json" > /dev/null
$py -m coverage report --include='python/rangtoy/*' > "$out/coverage-report.txt"
tail -60 "$out/coverage-report.txt"
