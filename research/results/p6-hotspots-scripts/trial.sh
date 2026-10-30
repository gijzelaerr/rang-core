#!/bin/bash
# Labelled trial: the coordinator's switch applied to core_cli.py, then reverted.
set -u
export PATH=$HOME/.cargo/bin:$PATH RUSTUP_TOOLCHAIN=1.93
cd ~/Worktrees/rang/p6-hotspots
O=outputs/p6-hotspots-20261030-09
mkdir -p $O
py=.venv/bin/python
sed -i 's/^from .flagging_trend import run as trend_run$/from .core_trend import run as trend_run/' python/rangtoy/core_cli.py
sed -i 's/            run_dir, inputs_dir, uvw_dir, iterations=int(iterations)$/            run_dir, inputs_dir, uvw_dir, iterations=int(iterations), ported=True/' python/rangtoy/core_cli.py
git diff -- python/rangtoy/core_cli.py > $O/switch.diff
unset RANG_P6
for stage in trend signal; do
  echo "$stage before $(cat /proc/loadavg)" >> $O/loads.txt
  if [ $stage = trend ]; then
    /usr/bin/time -f "%e %U %S %M" -o $O/trend.time $py -m rangtoy.core_cli trend $O/trend outputs/core-trend-mirror-20261029-01 > $O/trend.log 2>&1
  else
    /usr/bin/time -f "%e %U %S %M" -o $O/signal.time $py -m rangtoy.core_cli signal $O/signal outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01 > $O/signal.log 2>&1
  fi
  echo "$stage rc=$? after $(cat /proc/loadavg) time $(cat $O/$stage.time)" >> $O/loads.txt
done
$py -m rangtoy.core_cli compare trend $O/trend/result.json research/results/gain-tv-next-trend.json $O/compare-trend.json --posthoc-slope-scale > $O/compare-trend.log 2>&1; echo "compare trend rc=$?" >> $O/loads.txt
$py -m rangtoy.core_cli compare signal $O/signal/result.json research/results/gain-tv-next-signal.json $O/compare-signal.json > $O/compare-signal.log 2>&1; echo "compare signal rc=$?" >> $O/loads.txt
git checkout -- python/rangtoy/core_cli.py
git status --porcelain >> $O/loads.txt
$py examples/bench_p6_hotspots.py identity signal outputs/p6-hotspots-20261030-06/signal-base-1 $O/signal $O/identity-signal-vs-base.json >> $O/loads.txt
echo trial-done >> $O/loads.txt
