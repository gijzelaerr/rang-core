#!/usr/bin/env bash
# job.sh LABEL SLOTS MEM PY -- SCRIPT ARGS... : one DD10 step under the heavy lock, timed
R=D:/rang/outputs/dd10-20261126
W=C:/Users/gijsm/Worktrees/rang/dd10-gs
label=$1; slots=$2; mem=$3; PY=$4; shift 5
export RAYON_NUM_THREADS=$slots OMP_NUM_THREADS=$slots OPENBLAS_NUM_THREADS=$slots MKL_NUM_THREADS=$slots
cd $W
s=$(date +%s); echo "$label start $(date -Iseconds) slots=$slots mem=$mem py=$PY $*" >> $R/times.log
MSYS_NO_PATHCONV=1 python C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots $slots --mem $mem -- \
  $PY "$@" >> $R/logs/$label.log 2>&1
rc=$?
echo "$label end $(date -Iseconds) rc=$rc wall=$(( $(date +%s)-s ))s" >> $R/times.log
exit $rc
