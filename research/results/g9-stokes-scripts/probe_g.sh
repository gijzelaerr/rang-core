#!/usr/bin/env bash
# probe_g.sh BIN : GeMClean on the probe MS with the probe's WSClean configurations (development
# check of the semantics, before the protocol; not scored). Writes g-* beside each w-* directory.
set -euo pipefail
B=$1
O=/mnt/d/rang/outputs/g9-20261107-01-probe
W=$HOME/Worktrees/rang/fp-g9-stokes
run() {  # run NAME ARGS...
  local name=$1; shift
  mkdir -p "$O/g/$name"
  "$B" -size 512 512 -scale 3asec -weight briggs 0.5 -data-column DATA -field 0 -j 4 -mgain 0.8 \
    "$@" -name "$O/g/$name/g" "$O/probe.ms" > "$O/g/$name/log.txt" 2>&1 || { echo "FAIL $name"; tail -3 "$O/g/$name/log.txt"; }
}
run iq-join-fast -pol IQ -join-polarizations -niter 1 -gain 0.1
run iquv-c2 -pol IQUV -channels-out 2 -niter 0
run iquv-c2-join -pol IQUV -channels-out 2 -join-channels -niter 0
run iquv-c2-joinpol -pol IQUV -channels-out 2 -join-channels -join-polarizations -niter 1
run iquv-c2-nomf -pol IQUV -channels-out 2 -join-channels -no-mf-weighting -niter 0
run iquv-c1 -pol IQUV -niter 0
run q-c1 -pol Q -niter 0
run i-c1 -pol I -niter 0
run xxyy -pol xx,yy -niter 0
for d in "$O"/g/*/; do
  name=$(basename "$d"); echo "== $name"
  "$W/.venv/bin/python" "$W/research/results/g9-stokes-scripts/fits_cmp.py" "$d" "$O/$name"
done
