#!/usr/bin/env bash
# all.sh: DD15's prep, two lanes, score, and section 7 only if the frozen rule calls it
set -u
R=D:/rang/outputs/dd15-20261128; J="bash $R/scripts/job.sh"; S=tools/oracles/dd15/dd15.py
$J build 2 16 -- $S build $R || exit 1
$J gater 4 16 -- $S gater $R || exit 1
echo PREP_OK >> $R/times.log
( $J loop-ATG12 6 20 -- $S loop $R ATG12 && $J loop-QPG12 6 20 -- $S loop $R QPG12 ) > $R/logs/laneA.out 2>&1 &
sleep 60
( $J loop-QPG12-O 6 20 -- $S loop $R QPG12-O ) > $R/logs/laneB.out 2>&1 &
wait
echo LANES_DONE >> $R/times.log
$J score 2 8 -- $S score $R || exit 1
W=C:/Users/gijsm/Worktrees/rang/dd15-beam-gate
if $W/.venv/Scripts/python.exe -c "import json,sys; sys.exit(0 if json.load(open('$R/score.json')).get('real_check_called') else 1)"; then
  $J realprep 4 10 -- $S realprep $R || exit 1
  $J loop-R-QPG12 6 20 -- $S loop $R R-QPG12 || exit 1
  $J real 2 8 -- $S real $R || exit 1
  $J score2 2 8 -- $S score $R || exit 1
else
  echo "REAL_NOT_CALLED" >> $R/times.log
fi
echo ALL_DONE >> $R/times.log
