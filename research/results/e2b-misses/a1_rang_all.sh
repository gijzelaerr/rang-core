#!/bin/bash
# A1's rang side and comparison (Windows venv, 1 rayon thread); the caller books 1 slot.
export RAYON_NUM_THREADS=1
PY=C:/Users/gijsm/Worktrees/rang/e2b-arms/.venv/Scripts/python.exe
S=C:/Users/gijsm/Worktrees/rang/e2b-arms/research/results/e2b-misses
O='D:\rang\outputs\e2b-arms-20261114\a1'
t() { s=$(date +%s); "$@"; echo "rc=$? secs=$(( $(date +%s)-s )) :: $*"; }
t $PY $S/a1_rang.py rang "$O\mini.ms" "$O"
t $PY $S/a1_rang.py compare "$O"
