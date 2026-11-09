#!/usr/bin/env bash
# batch.sh OUT BIN SKY CFG... : GeMClean and WSClean on each configuration (research/g9-stokes.md);
# each run takes the heavy lock itself, so other agents can run in between.
set -u
here=$(dirname "$(readlink -f "$0")")
O=$1; B=$2; sky=$3; shift 3
mkdir -p "$O/runs"
for cfg in "$@"; do
  bash "$here/run_g.sh" "$O" "$B" "$sky" "$cfg"
  bash "$here/run_w.sh" "$O" "$sky" "$cfg"
done
