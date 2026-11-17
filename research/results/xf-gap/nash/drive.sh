#!/bin/bash
# SPDX-License-Identifier: MIT
# The xf-gap driver on nash (research/xf-gap.md section 5). Start detached:
#   cd ~/rang-data/outputs/xf-gap-20261117 && setsid nohup nice -n 19 ionice -c3 \
#     python3 ~/Github/rang/tools/heavy_lock.py run --slots 2 --mem 8 -- \
#     bash ~/Worktrees/rang/xf-gap/research/results/xf-gap/nash/drive.sh [STEPS...] \
#     > drive.log 2>&1 < /dev/null &
# Read: tail drive.log (last line "DRIVE END rc=N ..."), steps.log (one line per step).
WT=~/Worktrees/rang/xf-gap
O=~/rang-data/outputs/xf-gap-20261117
PY=$WT/.venv/bin/python
S="$PY $WT/research/results/xf-gap/xf_gap.py"
export RAYON_NUM_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 XFGAP_THREADS=2
export PATH=$WT/.venv/bin:$PATH
mkdir -p $O/logs
FAIL=0
step() {
  local name=$1; shift
  local t0=$(date +%s)
  "$@" > $O/logs/$name.log 2>&1
  local rc=$?
  echo "$(date -Is) rc=$rc $(( $(date +%s) - t0 ))s $name" >> $O/steps.log
  [ $rc -eq 0 ] || FAIL=$((FAIL + 1))
  return $rc
}
echo "DRIVE START $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg) steps: ${*:-all}"
ALL="gen arms casa h0 ladder mirror gauge score"
for st in ${*:-$ALL}; do
  case $st in
  gen)
    for s in dev held held4 dev90; do
      [ -d $O/truth-$s/a1-poldx-twin.ms ] || step gen-$s $S gen $s || exit 1
    done
    step psi-held $S psi held; step psi-dev $S psi dev ;;
  arms)
    for s in held dev held4 dev90; do
      for a in m90_noavg m90; do step rang-$s-$a $S rang $s $a; done
    done
    step rang-held-gpol8 $S rang held gpol8 ;;
  casa)
    for s in held dev held4 dev90; do step casa-$s $S casa $s; done
    step casa-held-gpol8 $S casa held gpol8 ;;
  h0)
    for s in held dev; do step rangcal-$s $S rangcal $s && step h0-$s $S h0 $s; done ;;
  ladder)
    step ladder-held-noavg $S ladder held 0
    step ladder-held-avg $S ladder held 1
    step ladder-dev-noavg $S ladder dev 0 ;;
  mirror)
    step mirror-held $S mirror held; step mirror-dev $S mirror dev ;;
  gauge)
    step gauge-held $S gauge held; step gauge-dev $S gauge dev ;;
  score)
    step score $S score $O/results.json ;;
  *) echo "unknown step $st"; FAIL=$((FAIL + 1)) ;;
  esac
done
echo "DRIVE END rc=$FAIL $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
