H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
PY=$HOME/Build/tmp/20261120-dl4b-torch/bin/python
S=$HOME/Build/tmp/20261121-dl4b-step1
$PY $H/examples/dl4b_train1.py train $S/skies /mnt/d/rang/dl4b-step1/smoke --seed 99 --hours 0.5 --steps-total 12000 --steps-max 1000 --batch 8 --yield-window 06:00-06:50 --yield-window 2026-11-21T20:50/2026-11-22T06:30 --yield-window 2026-11-22T06:50/2026-11-22T10:00
