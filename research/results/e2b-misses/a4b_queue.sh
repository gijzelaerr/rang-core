#!/bin/bash
# Arm A4b (research/e2b-misses.md 9.11), in WSL: unit on, one WSClean run with
# -no-small-inversion, unit off; each step under the main checkout's heavy_lock.py.
set -u
S=$(cd "$(dirname "$0")" && pwd)
L=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
python3 $L run --slots 1 --mem 2 -- bash "$S/a4_run.sh" unit on || exit 1
python3 $L run --slots 4 --mem 10 -- bash "$S/a4_run.sh" wsclean-nosi 2 J1833m2103 1e-06
rc=$?
python3 $L run --slots 1 --mem 2 -- bash "$S/a4_run.sh" unit off
exit $rc
