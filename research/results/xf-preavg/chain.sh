#!/bin/bash
# The xf-preavg chain (research/xf-preavg.md section 3). heavy_lock from the
# main checkout; the scripts in this worktree's venv.
#   chain.sh gen | arms     (each takes its own lock ticket)
export MSYS_NO_PATHCONV=1
LOCKPY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
L="$LOCKPY C:/Users/gijsm/Github/rang/tools/heavy_lock.py run"
BASH_EXE="C:/Program Files/Git/usr/bin/bash.exe"
WT=C:/Users/gijsm/Worktrees/rang/xf-preavg
PY=$WT/.venv/Scripts/python.exe
S="$PY $WT/research/results/xf-preavg/xf_preavg.py"
R=$WT/research/results/xf-preavg
OUT=D:/rang/outputs/xf-preavg-20261117-01-sim
DEV=D:/rang/outputs/chi-offset-20261113-02-sim/truth-control
mkdir -p $OUT
export RAYON_NUM_THREADS=4 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
t() { local s=$(date +%s); "$@"; local rc=$?; echo "$(date -Is) rc=$rc $(( $(date +%s)-s ))s: $*" >> $OUT/timings.log; return $rc; }
case "$1" in
gen)
  t $L --slots 4 --mem 4 -- $S gen $OUT > $OUT/gen-held.log 2>&1
  [ -d $OUT/truth-control ] || t $S copydev $OUT $DEV
  t $S psi $OUT held $R/psi-held.json > $OUT/psi-held.log 2>&1
  t $S psi $OUT control $R/psi-control.json > $OUT/psi-control.log 2>&1
  t $S casadefaults $OUT > $OUT/casadefaults.log 2>&1
  cp $OUT/casa-polcal-defaults.txt $R/ ;;
arms) t $L --slots 4 --mem 10 -- "$BASH_EXE" $R/chain.sh batch ;;
batch)
  for tr in control held; do
    for a in m90 m90_noavg; do
      [ -f $OUT/rang-$tr-$a/chi.json ] || t $S rang $OUT $tr $a > $OUT/arm-rang-$tr-$a.log 2>&1
    done
    [ -f $OUT/casa-$tr-m90/chi.json ] || t $S casa $OUT $tr > $OUT/arm-casa-$tr-m90.log 2>&1
  done
  t $S score $OUT $R/results.json > $OUT/score.log 2>&1 ;;
*) echo "usage: chain.sh gen|arms"; exit 2 ;;
esac
echo "STAGE $1 DONE $(date -Is)"
