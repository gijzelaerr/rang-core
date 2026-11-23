#!/bin/bash
# Arm D (gate3c-rerun.md sections 3, 5): wait for F7's timing chain (pid 22496) to exit, then run chain.sh from d-dirty.
RR=D:/rang/outputs/gate3c-rerun-20261123
echo "$(date -Iseconds) armd waiter: waiting for pid 22496 (F7 timing chain)" >> $RR/armd.log
while ps -p 22496 > /dev/null 2>&1; do sleep 180; done
echo "$(date -Iseconds) armd waiter: pid 22496 gone, D: free $(df -h /d | tail -1 | awk '{print $4}')" >> $RR/armd.log
cd $RR
FIRST=d-dirty SCRIPTS=C:/Users/gijsm/Github/rang/research/results/e2-acceptance-scripts LEG=e2a MS=$RR/e2a.ms R=$RR PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe LEGPY=C:/Users/gijsm/Build/tmp/20261123-gate3c-rerun/e2a-venv/Scripts/python.exe LOCK=C:/Users/gijsm/Github/rang/tools/heavy_lock.py LOCKPY=python SELFCAL_VERSION=flags.rang_selfcal_20261115T161755Z ARCHIVED_NOSI=D:/rang/outputs/e2a-20261115/wsclean3c-a-nosi CLEAN=0 DARM=1 bash C:/Users/gijsm/Worktrees/rang/gate3c-rerun/research/results/gate3c-rerun/chain.sh
echo "$(date -Iseconds) armd chain rc=$?" >> $RR/armd.log
