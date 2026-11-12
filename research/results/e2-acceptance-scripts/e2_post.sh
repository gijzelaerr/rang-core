#!/bin/sh
# E2's post-run steps in their fixed order (e2_post.py ORDER; research/e2-acceptance.md
# 6.5, 6.7): everything that reads rang's columns or post-stage flags runs before
# `restore`. Each step is a shared job of the main checkout's heavy_lock.
#   sh e2_post.sh MS R INPUT.json STRATEGY [FIRST_STEP] [LAST_STEP]
# For E2-B: then e2_casa3b.py run (3b's CASA arm, on R/casa/); its scores, 3c and
# the rows are sealed until the 6.7 amendment commit.
ms=$1 r=$2 input=$3 strategy=$4 first=${5:-gate1} last=${6:-tricolour}
cd /c/Users/gijsm/Worktrees/rang/fp-e2-acceptance || exit 1
export PYTHONUTF8=1
py=$(cygpath -w "$PWD/.venv/Scripts/python.exe")
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
s=research/results/e2-acceptance-scripts/e2_post.py
on=0
for step in gate1 archive wcs casacore casa-ro wsclean0 daskms wsclean3c copy prep applycal compare restore tricolour; do
  [ "$step" = "$first" ] && on=1
  [ $on = 1 ] || continue
  case $step in
    restore) extra="$input" ;;
    tricolour) extra="$input $strategy" ;;
    *) extra= ;;
  esac
  t0=$(date +%s)
  # shellcheck disable=SC2086
  "$py" "$lock" run --slots 8 --mem 16 -- "$py" "$s" "$step" "$ms" "$r" $extra >> "$r/post-steps.log" 2>&1
  rc=$?
  echo "$(date -Is) $step rc=$rc $(( $(date +%s) - t0 ))s" >> "$r/post-steps.log"
  echo "$step rc=$rc $(( $(date +%s) - t0 ))s"
  [ $rc = 0 ] || exit $rc
  [ "$step" = "$last" ] && break
done
