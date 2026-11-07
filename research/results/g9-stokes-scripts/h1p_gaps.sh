#!/usr/bin/env bash
# h1p_gaps.sh : where H1p's largest criterion-E differences sit (Q2 U and Q, Q0 I).
W=$HOME/Worktrees/rang/fp-g9-stokes
P=$W/.venv/bin/python
S=$W/research/results/g9-stokes-scripts
O=/mnt/d/rang/outputs/g9-20261107-03
for a in "Q2 U" "Q2 Q" "Q2 I" "Q0 I"; do
  echo "== $a"
  # shellcheck disable=SC2086
  $P $S/gap_where.py $O H1p $a $O/data/H1p.json
done
