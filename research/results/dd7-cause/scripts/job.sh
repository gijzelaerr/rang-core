#!/usr/bin/env bash
# job.sh LABEL SLOTS MEM -- dd7.py|dd6.py ARGS... : one DD7 step under the heavy lock, timed
R=D:/rang/outputs/dd7-20261125
W=C:/Users/gijsm/Worktrees/rang/dd7-cause
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
label=$1; slots=$2; mem=$3; shift 4
tool=$1; shift
export RAYON_NUM_THREADS=$slots
cd $W
s=$(date +%s); echo "$label start $(date -Iseconds) slots=$slots mem=$mem $tool $*" >> $R/times.log
MSYS_NO_PATHCONV=1 python C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots $slots --mem $mem -- \
  $PY tools/oracles/${tool%.py}/$tool "$@" >> $R/logs/$label.log 2>&1
rc=$?
echo "$label end $(date -Iseconds) rc=$rc wall=$(( $(date +%s)-s ))s" >> $R/times.log
exit $rc
