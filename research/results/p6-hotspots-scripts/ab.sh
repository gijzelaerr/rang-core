#!/bin/bash
# Interleaved A/B (criterion 6) plus identity (1, 2) and comparators (3) per pair.
# usage: ab.sh <outdir> <pairs>
set -u
export PATH=$HOME/.cargo/bin:$PATH RUSTUP_TOOLCHAIN=1.93
cd ~/Worktrees/rang/p6-hotspots
out=$1; pairs=$2
mkdir -p "$out"
py=.venv/bin/python
echo "head $(git rev-parse HEAD) status $(git status --porcelain | tr '\n' ' ')" > "$out/provenance.txt"
timed() {  # label stage rep cmd...
  local label=$1 stage=$2 rep=$3; shift 3
  local d="$out/$stage-$label-$rep" before after
  before=$(cut -d' ' -f1-3 /proc/loadavg)
  if [ $stage = trend ]; then extra=("$M"); else extra=("${SI[@]}"); fi
  /usr/bin/time -f "%e %U %S %M" -o "$d.time" "$@" "$d" "${extra[@]}" > "$d.log" 2>&1
  local rc=$?
  after=$(cut -d' ' -f1-3 /proc/loadavg)
  echo -e "$stage\t$label\t$rep\t$rc\t$(tail -n 1 $d.time)\t$before\t$after" >> "$out/timings.tsv"
}
T=(.venv/bin/python examples/bench_p6_hotspots.py trend)
M=outputs/core-trend-mirror-20261029-01
SIG=(.venv/bin/python -m rangtoy.core_cli signal)
SI=(outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01)
for rep in $(seq 1 "$pairs"); do
  if [ $((rep % 2)) = 1 ]; then order="base new"; else order="new base"; fi
  for arm in $order; do
    if [ $arm = base ]; then timed base trend $rep "${T[@]}" frozen; else timed new trend $rep "${T[@]}" ported; fi
  done
  for arm in $order; do
    if [ $arm = base ]; then timed base signal $rep env -u RANG_P6 "${SIG[@]}"; else timed new signal $rep env RANG_P6=1 "${SIG[@]}"; fi
  done
  $py examples/bench_p6_hotspots.py identity trend "$out/trend-base-$rep" "$out/trend-new-$rep" "$out/identity-trend-$rep.json" >> "$out/checks.log" 2>&1
  $py examples/bench_p6_hotspots.py identity signal "$out/signal-base-$rep" "$out/signal-new-$rep" "$out/identity-signal-$rep.json" >> "$out/checks.log" 2>&1
  for arm in base new; do
    $py -m rangtoy.core_cli compare trend "$out/trend-$arm-$rep/result.json" research/results/gain-tv-next-trend.json "$out/compare-trend-$arm-$rep.json" --posthoc-slope-scale >> "$out/checks.log" 2>&1
    $py -m rangtoy.core_cli compare signal "$out/signal-$arm-$rep/result.json" research/results/gain-tv-next-signal.json "$out/compare-signal-$arm-$rep.json" >> "$out/checks.log" 2>&1
  done
done
echo done >> "$out/checks.log"
