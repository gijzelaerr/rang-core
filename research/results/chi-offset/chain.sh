#!/bin/bash
# The chi-offset chain (research/chi-offset.md 7), resumed 2026-11-13.
# heavy_lock from the main checkout; the scripts in this worktree's venv
# (rang-core next to its python). Short arms are batched in one lock ticket
# each (the queue wait, ~20 min, dwarfs the 8-30 s sim arms).
#   chain.sh gen | gate | sim | luno-build | luno-rang | luno-casa
#   chain.sh batch-sim | batch-luno-rang | batch-luno-casa   (run inside a ticket)
export MSYS_NO_PATHCONV=1
LOCKPY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
L="$LOCKPY C:/Users/gijsm/Github/rang/tools/heavy_lock.py run"
BASH_EXE="C:/Program Files/Git/usr/bin/bash.exe"
WT=C:/Users/gijsm/Github/rang/.claude/worktrees/chi-offset-80cb6a
PY=$WT/.venv/Scripts/python.exe
W=$WT/research/results/chi-offset
SIM=D:/rang/outputs/chi-offset-20261113-02-sim
LUNO=D:/rang/outputs/chi-offset-20261113-03-luno
mkdir -p $SIM $LUNO-s17 $LUNO-s1
export RAYON_NUM_THREADS=4 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
fail=0
run() { "$@"; rc=$?; [ $rc = 0 ] || { echo "FAILED rc=$rc: $*"; fail=1; }; return $rc; }
pids=()
waitall() { for p in "${pids[@]}"; do wait $p || fail=1; done; pids=(); }
# each arm's own log (native writers do not append safely to a shared file)
arm() { local log=$1; shift; echo "$(date -Is) start $*"; run "$@" > "$log" 2>&1; echo "$(date -Is) end rc=$rc $*"; }
case "$1" in
gen)
  for t in control feed0 revpsi; do
    run $L --slots 4 --mem 4 -- $PY $W/sim_chi.py gen $t $SIM >> $SIM/gen-$t.log 2>&1 & pids+=($!)
  done
  waitall ;;
gate)
  run $L --slots 4 --mem 4 -- $PY $W/sim_chi.py rang $SIM control m90 >> $SIM/arms.log 2>&1 ;;
sim) run $L --slots 4 --mem 6 -- "$BASH_EXE" $W/chain.sh batch-sim ;;
batch-sim)
  for t in control feed0 revpsi; do
    for a in m90 null m90_noavg null_noavg; do
      [ -f $SIM/rang-$t-$a/chi.json ] && continue
      arm $SIM/arm-rang-$t-$a.log $PY $W/sim_chi.py rang $SIM $t $a
    done
  done
  [ -f $SIM/rang-control-gpol_noparang/chi.json ] || arm $SIM/arm-rang-control-gpol_noparang.log $PY $W/sim_chi.py rang $SIM control gpol_noparang
  for t in control feed0 revpsi; do
    for a in m90 feedms; do
      [ -f $SIM/casa-$t-$a/chi.json ] && continue
      arm $SIM/arm-casa-$t-$a.log $PY $W/sim_chi.py casa $SIM $t $a
    done
  done ;;
luno-build)
  for u in s17 s1; do
    run $L --slots 4 --mem 8 -- $PY $W/luno_rerun.py build $LUNO-$u >> $LUNO-$u.build-runner.log 2>&1 & pids+=($!)
  done
  waitall ;;
luno-rang) RAYON_NUM_THREADS=8 run $L --slots 8 --mem 16 -- "$BASH_EXE" $W/chain.sh batch-luno-rang ;;
batch-luno-rang)
  export RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8
  for u in s17 s1; do
    for a in null m90 null_noavg; do
      [ -f $LUNO-$u/rang-$a/chi-all.json ] && continue
      arm $LUNO-$u/arm-rang-$a.log $PY $W/luno_rerun.py rang $LUNO-$u $a
      rm -rf $LUNO-$u/rang-$a/sim.ms   # scored; the tables stay in sim.ms.rang-run
    done
  done ;;
luno-casa) run $L --slots 4 --mem 12 -- "$BASH_EXE" $W/chain.sh batch-luno-casa ;;
batch-luno-casa)
  for u in s17 s1; do
    for a in feed0 m90; do
      [ -f $LUNO-$u/casa-$a/chi-all.json ] && continue
      arm $LUNO-$u/arm-casa-$a.log $PY $W/luno_rerun.py casa $LUNO-$u $a
      rm -rf $LUNO-$u/casa-$a/sim.ms
    done
  done ;;
*) echo "usage: chain.sh gen|gate|sim|luno-build|luno-rang|luno-casa"; exit 2 ;;
esac
echo "STAGE $1 DONE fail=$fail $(date -Is)"
exit $fail
