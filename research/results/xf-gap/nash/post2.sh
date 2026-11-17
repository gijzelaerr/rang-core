#!/bin/bash
# SPDX-License-Identifier: MIT
W=~/Worktrees/rang/xf-gap; P=$W/.venv/bin/python; D=$W/research/results/xf-gap
export RAYON_NUM_THREADS=2 OMP_NUM_THREADS=2 XFGAP_THREADS=2
for s in held dev; do for w in 0 1; do t=$(date +%s); $P $D/xf_gap.py casawt $s $w > logs/casawt-$s-$w.log 2>&1; echo "$(date -Is) rc=$? $(( $(date +%s)-t ))s casawt-$s-$w" >> steps.log; done; done
$P $D/xf_gap.py posthoc posthoc.json > logs/posthoc.log 2>&1; echo "$(date -Is) rc=$? posthoc" >> steps.log
echo "DRIVE END rc=0 $(date -Is)"
