#!/usr/bin/env bash
# S1 py-spy and perf profiles (distribution only; walls come from suite.sh).
# Usage: bash pyspy.sh outputs/simplification-review-20261030-NN
set -uo pipefail
cd ~/Worktrees/rang/simplification-review
export PATH=$HOME/.cargo/bin:$PATH
export RUSTUP_TOOLCHAIN=1.93
out=$1; shift
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out"
py=.venv/bin/python
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/s1
spy() {
  local name=$1; shift
  echo "## py-spy $name"
  /usr/bin/time -f '%e s %M KB %P' .venv/bin/py-spy record --native --idle --rate 250 --format raw -o "$out/$name.raw.txt" -- "$@" > "$out/$name.log" 2>&1
  tail -1 "$out/$name.log"
}
spy campaign $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign" --images original
spy precondition $py examples/precondition_luno_campaign.py "$out/precondition"
spy kcheck $py examples/check_luno_campaign.py outputs/core-k-20261030-01 outputs/core-k-20261030-00-precondition "$out/kcheck"
spy section6 $py examples/prototype_section6.py "$out/section6"
spy section6-check $py examples/check_section6.py "$out/section6" outputs/core-section6-oracle-20261029-01 400 "$out/section6-check"
spy actions $py -m rangtoy.core_cli actions "$out/actions" outputs/core-phase3-actions-inputs-20261029-01
spy injections $py -m rangtoy.core_cli injections "$out/injections" outputs/tv-injections-wsl-20261029-01
spy signal $py -m rangtoy.core_cli signal "$out/signal" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01
spy trend $py -m rangtoy.core_cli trend "$out/trend" outputs/simplification-review-20261030-01/trend-mirror
spy imaging $py examples/run_core_imaging.py "$out/imaging"
# One SVG flamegraph of the campaign chain.
.venv/bin/py-spy record --native --rate 100 --format flamegraph -o "$out/campaign.svg" -- $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign-svg" --images original > "$out/campaign-svg.log" 2>&1
# perf: CPU samples by shared object and symbol (user space only).
echo "## perf campaign"
perf record -e cpu-clock:u -F 999 -o "$out/campaign.perf.data" -- $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch "$out/campaign-perf" --images original > "$out/campaign-perf.log" 2>&1
perf report -i "$out/campaign.perf.data" --no-children --sort dso --stdio 2>/dev/null | grep -v "^#" | grep -v "^$" | head -25 > "$out/campaign.perf-dso.txt"
perf report -i "$out/campaign.perf.data" --no-children --sort dso,symbol --stdio 2>/dev/null | grep -v "^#" | grep -v "^$" | head -60 > "$out/campaign.perf-symbols.txt"
perf report -i "$out/campaign.perf.data" --no-children --sort comm,tid --stdio 2>/dev/null | grep -v "^#" | grep -v "^$" | head -30 > "$out/campaign.perf-threads.txt"
rm -f "$out/campaign.perf.data"
echo "## perf imaging (C gridder run)"
perf record -e cpu-clock:u -F 499 -o "$out/c.perf.data" -- $py examples/run_core_gridder.py outputs/tv-next-imaging-wsl-20261029-01 outputs/core-c-20261029-01 "$out/c" > "$out/c-perf.log" 2>&1
perf report -i "$out/c.perf.data" --no-children --sort dso,symbol --stdio 2>/dev/null | grep -v "^#" | grep -v "^$" | head -40 > "$out/c.perf-symbols.txt"
rm -f "$out/c.perf.data"
echo "## done"
$py $S/classify.py "$out"/*.raw.txt > "$out/classified.json"
ls -la "$out"
