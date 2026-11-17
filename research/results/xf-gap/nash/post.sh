#!/bin/bash
# SPDX-License-Identifier: MIT
W=~/Worktrees/rang/xf-gap; P=$W/.venv/bin/python; D=$W/research/results/xf-gap; O=~/rang-data/outputs/xf-gap-20261117
export RAYON_NUM_THREADS=2 OMP_NUM_THREADS=2
echo START $(date -Is)
for s in held dev; do
 for c in p1 p2; do t=$(date +%s); $P $D/xf_gap.py $c $s > logs/$c-$s.log 2>&1; echo "$(date -Is) rc=$? $(( $(date +%s)-t ))s $c-$s" >> steps.log; done
 t=$(date +%s); $P $D/xf_probe.py $s probe-$s.json > logs/probe-$s.log 2>&1; echo "$(date -Is) rc=$? $(( $(date +%s)-t ))s probe-$s" >> steps.log
done
$P $D/xf_gap.py posthoc posthoc.json > logs/posthoc.log 2>&1; echo "$(date -Is) rc=$? posthoc" >> steps.log
echo "DRIVE END rc=0 $(date -Is)"
