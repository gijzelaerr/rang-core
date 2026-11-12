#!/bin/sh
# E1b: the control and the scorer of the two m32 arms, rerun after e1b_all.sh's
# first attempt failed at the control's gemclean call (G8's command; e1b_run.py
# control now expands it). research/e2-acceptance.md section 4.
J=research/results/e2-acceptance-scripts/e2_job.sh
S=research/results/e2-acceptance-scripts
O='D:\rang\outputs'
cd /c/Users/gijsm/Worktrees/rang/fp-e2-acceptance || exit 1
for arm in 04-e1b-auto:m022,m023,m024 05-e1b-m000:m000; do
  run=${arm%%:*}; ref=${arm#*:}; R="$O\e2-20261110-$run"; L="$R\e1b.log"
  [ -f "$R/result-e1b.json" ] && continue
  $J "$L" py $S/e1b_run.py control "$R" || continue
  $J "$L" py $S/e1b_score.py chain "$R" --refant "$ref" --tricolour "$O\e1-20261109-04-tricolour"
done
