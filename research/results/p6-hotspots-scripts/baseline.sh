#!/bin/bash
# usage: baseline.sh <outdir> <label> <stage...>   ; env P6 passed through
set -u
export PATH=$HOME/.cargo/bin:$PATH RUSTUP_TOOLCHAIN=1.93
cd ~/Worktrees/rang/p6-hotspots
out=$1; label=$2; shift 2
mkdir -p "$out"
py=.venv/bin/python
for rep in 1 2 3; do
  for stage in "$@"; do
    d="$out/$label-$stage-$rep"
    load=$(cut -d' ' -f1-3 /proc/loadavg)
    if [ "$stage" = trend ]; then
      cmd=($py -m rangtoy.core_cli trend "$d" outputs/core-trend-mirror-20261029-01)
    else
      cmd=($py -m rangtoy.core_cli signal "$d" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01)
    fi
    /usr/bin/time -f "%e %U %S %M" -o "$d.time" "${cmd[@]}" > "$d.log" 2>&1
    rc=$?
    echo -e "$label\t$stage\t$rep\t$rc\t$(cat $d.time | tail -1)\t$load\t$(cut -d' ' -f1-3 /proc/loadavg)" >> "$out/timings.tsv"
  done
done
