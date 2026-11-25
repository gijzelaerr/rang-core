#!/usr/bin/env bash
# job.sh LABEL SLOTS MEM -- dd6.py ARGS... : one DD6 step under the heavy lock, timed
R=D:/rang/outputs/dd6-20261125
W=C:/Users/gijsm/Worktrees/rang/dd6-d0
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
label=$1; slots=$2; mem=$3; shift 4
export RAYON_NUM_THREADS=$slots
cd $W
s=$(date +%s); echo "$label start $(date -Iseconds) slots=$slots mem=$mem args=$*" >> $R/times.log
MSYS_NO_PATHCONV=1 python C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots $slots --mem $mem -- \
  $PY tools/oracles/dd6/dd6.py "$@" >> $R/logs/$label.log 2>&1
rc=$?
echo "$label end $(date -Iseconds) rc=$rc wall=$(( $(date +%s)-s ))s" >> $R/times.log
exit $rc
