#!/bin/bash
# solver-flags stage 4: arms M0, M1, M2 on E2-N and A1 from the branch's worktree, then the
# QuartiCal oracle cases (cut from M0). Any non-zero exit writes logs/FAILED.
S=$(dirname "$0")
R=$HOME/rang-data/outputs/solver-flags-20261125
mkdir -p "$R/logs"
fail() { echo "$(date -Is) FAILED $1 rc=$2" >> "$R/logs/FAILED"; }
bash "$S/sf.sh" setup > "$R/logs/setup2.out" 2>&1 || { fail setup2 $?; exit 1; }
( bash "$S/sf.sh" e2n M0 > "$R/logs/e2n-M0.out" 2>&1 || fail e2n-M0 $?
  bash "$S/sf.sh" oracle e2n > "$R/logs/oracle-e2n.out" 2>&1 || fail oracle-e2n $? ) &
for arm in M1 M2; do
  bash "$S/sf.sh" e2n $arm > "$R/logs/e2n-$arm.out" 2>&1 || fail e2n-$arm $? &
done
( while [ ! -e "$R/done.a1-gen" ]; do sleep 300; done
  for arm in M0 M1 M2; do bash "$S/sf.sh" a1 $arm > "$R/logs/a1-$arm.out" 2>&1 || fail a1-$arm $?; done
  bash "$S/sf.sh" oracle a1 > "$R/logs/oracle-a1.out" 2>&1 || fail oracle-a1 $? ) &
wait
echo "$(date -Is) launch2 done" >> "$R/logs/driver.log"
