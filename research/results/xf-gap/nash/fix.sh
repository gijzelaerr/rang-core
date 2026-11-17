#!/bin/bash
# SPDX-License-Identifier: MIT
W=~/Worktrees/rang/xf-gap; P=$W/.venv/bin/python; D=$W/research/results/xf-gap
export RAYON_NUM_THREADS=2 OMP_NUM_THREADS=2 XFGAP_THREADS=2 PATH=$W/.venv/bin:$PATH
run() { local n=$1; shift; t=$(date +%s); "$@" > logs/$n.log 2>&1; echo "$(date -Is) rc=$? $(( $(date +%s)-t ))s $n" >> steps.log; }
for s in dev held; do run f1-$s $P $D/xf_gap.py f1 $s; done
for s in held held4 dev; do for a in calwt calwt_avg; do run rang-$s-$a $P $D/xf_gap.py rang $s $a; done; done
run fixscore $P $D/xf_gap.py fixscore fix.json
echo "DRIVE END rc=0 $(date -Is)"
