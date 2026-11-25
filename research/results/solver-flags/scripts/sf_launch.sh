#!/bin/bash
# solver-flags: the arms that need no new code (R on E2-N and A1) and the QuartiCal venv.
# Arm R runs from a frozen worktree (SF_WT, detached at the note's scripts commit) so that
# later code on the branch never reaches a running R. Any non-zero exit writes logs/FAILED.
S=$(dirname "$0")
R=$HOME/rang-data/outputs/solver-flags-20261125
mkdir -p "$R/logs"
fail() { echo "$(date -Is) FAILED $1 rc=$2" >> "$R/logs/FAILED"; }
export SF_WT=$HOME/Worktrees/rang/solver-flags-base
bash "$S/sf.sh" setup > "$R/logs/setup.out" 2>&1 || { fail setup $?; exit 1; }
bash "$S/sf.sh" qcvenv > "$R/logs/qcvenv.out" 2>&1 || fail qcvenv $? &
bash "$S/sf.sh" e2n R > "$R/logs/e2n-R.out" 2>&1 || fail e2n-R $? &
( bash "$S/sf.sh" a1-gen > "$R/logs/a1-gen.out" 2>&1 && bash "$S/sf.sh" a1 R > "$R/logs/a1-R.out" 2>&1 ) || fail a1-R $? &
wait
echo "$(date -Is) launch done" >> "$R/logs/driver.log"
