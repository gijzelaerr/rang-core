#!/usr/bin/env bash
# job.sh LABEL SLOTS MEM -- SCRIPT ARGS... : one DD9 step under the heavy lock, timed
R=D:/rang/outputs/dd9-20261126
W=C:/Users/gijsm/Worktrees/rang/dd9-solver
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
label=$1; slots=$2; mem=$3; shift 4
export RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots OPENBLAS_NUM_THREADS=$slots MKL_NUM_THREADS=$slots
cd $W
s=$(date +%s); echo "$label start $(date -Iseconds) slots=$slots mem=$mem $*" >> $R/times.log
MSYS_NO_PATHCONV=1 python C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots $slots --mem $mem -- \
  $PY "$@" >> $R/logs/$label.log 2>&1
rc=$?
echo "$label end $(date -Iseconds) rc=$rc wall=$(( $(date +%s)-s ))s" >> $R/times.log
exit $rc
