#!/bin/bash
# stop28-default amendment 4: the confirmation leg. Stages in the amendment's order; each stage
# runs only if the previous exited 0. Log logs/run-confirm.log, last line ALL-END rc=N.
source ~/.rang-env.sh
export O=~/rang-data/outputs/stop28-confirm-20261118
export PREV=~/rang-data/outputs/stop28-default-20261117
W=~/Worktrees/rang/stop28-default
L=$O/logs
mkdir -p $L
run() { echo "$(date +%F\ %T) start $1"; nice -n 19 ionice -c3 $W/.venv/bin/python $W/examples/stop28_default.py $1 > $L/driver-$1.log 2>&1; rc=$?; echo "DRIVER-END $1 rc=$rc" >> $L/driver-$1.log; echo "$(date +%F\ %T) end $1 rc=$rc"; return $rc; }
git -C $W log --oneline -1 > $O/driver-commit.txt
run c-bin || { echo ALL-END rc=1; exit 1; }
run c-seen || { echo ALL-END rc=2; exit 2; }
run c-simulate || { echo ALL-END rc=3; exit 3; }
( run c-new ) & p1=$!
( run c-wsclean ) & p2=$!
wait $p1; r1=$?; wait $p2; r2=$?
[ $r1 -eq 0 ] && [ $r2 -eq 0 ] || { echo ALL-END rc=4; exit 4; }
run c-score || { echo ALL-END rc=5; exit 5; }
run c-table || { echo ALL-END rc=6; exit 6; }
echo ALL-END rc=0
