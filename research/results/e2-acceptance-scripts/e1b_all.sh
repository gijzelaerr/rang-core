#!/bin/sh
# E1b, every arm in order (research/e2-acceptance.md section 3), each step through
# e2_job.sh (heavy lock; START/END/rc in the arm's log). Twins first (seconds).
J=research/results/e2-acceptance-scripts/e2_job.sh
S=research/results/e2-acceptance-scripts
O='D:\rang\outputs'
cd /c/Users/gijsm/Worktrees/rang/fp-e2-acceptance || exit 1
for arm in 06-e1b-twin-auto:m022,m023,m024 07-e1b-twin-m000:m000; do
  run=${arm%%:*}; ref=${arm#*:}; R="$O\e2-20261110-$run"; L="$R\e1b.log"
  [ "$run" = 06-e1b-twin-auto ] && ref=$(.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'python'); from rang import cal_refant; print(','.join(cal_refant.caracal_refant(r'$R\ms\a1-small-twin.ms').names))")
  $J "$L" py -m rang.core_cli run "$R\config.yaml" "$R\ms\a1-small-twin.ms"
  $J "$L" py $S/e1b_score.py twin "$R" --refant "$ref"
done
for arm in 04-e1b-auto:m022,m023,m024 05-e1b-m000:m000; do
  run=${arm%%:*}; ref=${arm#*:}; R="$O\e2-20261110-$run"; L="$R\e1b.log"
  $J "$L" py -m rang.core_cli run "$R\config.yaml" "$R\ms\a1-full-m32.ms" || continue
  $J "$L" py $S/e1b_run.py control "$R"
  $J "$L" py $S/e1b_score.py chain "$R" --refant "$ref" --tricolour "$O\e1-20261109-04-tricolour"
done
