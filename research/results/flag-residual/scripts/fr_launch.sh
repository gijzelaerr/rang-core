#!/bin/bash
# flag-residual: setup, then the E2-N and A1 arms in parallel; any non-zero exit writes logs/FAILED
# (session A's watcher wakes on it).
S=$(dirname "$0")
R=$HOME/rang-data/outputs/flag-residual-20261121
mkdir -p "$R/logs"
fail() { echo "$(date -Is) FAILED $1 rc=$2" >> "$R/logs/FAILED"; }
bash "$S/fr.sh" setup > "$R/logs/setup.out" 2>&1 || { fail setup $?; exit 1; }
bash "$S/fr.sh" e2n > "$R/logs/e2n.out" 2>&1 || fail e2n $? &
bash "$S/fr.sh" a1 > "$R/logs/a1.out" 2>&1 || fail a1 $? &
wait
echo "$(date -Is) launch done" >> "$R/logs/driver.log"
