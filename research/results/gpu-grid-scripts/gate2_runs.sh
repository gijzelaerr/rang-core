#!/usr/bin/env bash
# Gate 2 of research/gpu-grid.md: GeMClean with -gpu on every sky, both forms (the CPU arm is
# the Gate 0 baseline, byte-identical to this build without -gpu). Usage: gate2_runs.sh BIN BUDGET
BIN=$1; BUD=$2
W=/c/Users/gijsm/Worktrees/rang/gpu-grid
O=D:/rang/outputs/20261116-gpu-grid/gate2/gpu
mkdir -p $O
for sky in s1 s2 s3 h1 h2 h3 h4; do
  for form in coarse fine; do
    nvidia-smi --query-gpu=memory.used --format=csv,noheader > $O/$sky-$form.gpu
    bash $W/outputs/gpu-grid/run_sky.sh $BIN $O $sky-$form $sky $form 8 -gpu -gpu-memory $BUD
    grep -h "components\|^gpu:" $O/$sky-$form.log | cut -c1-160
  done
done
