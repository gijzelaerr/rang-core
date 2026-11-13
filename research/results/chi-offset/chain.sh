#!/bin/bash
export MSYS_NO_PATHCONV=1
cd /c/Users/gijsm/Github/rang
PY=.venv/Scripts/python.exe
L="$PY tools/heavy_lock.py run"
W=C:/Users/gijsm/Github/rang/.claude/worktrees/chi-offset-80cb6a/research/results/chi-offset
SIM=D:/rang/outputs/chi-offset-20261113-02-sim
LUNO=D:/rang/outputs/chi-offset-20261113-03-luno
mkdir -p $LUNO
# wait for gen job (separate) to finish: truth MSs must exist
while [ ! -d $SIM/truth-revpsi/a1-poldx-twin.ms ] || ! grep -q "gen revpsi" $SIM/sim_chi.log 2>/dev/null; do
  grep -q "failed" $SIM/gen.log 2>/dev/null && break; sleep 60; done
for t in control feed0 revpsi; do
  for a in m90 null; do $L --slots 4 --mem 4 -- $PY $W/sim_chi.py rang $SIM $t $a >> $SIM/arms.log 2>&1; done
done
$L --slots 4 --mem 4 -- $PY $W/sim_chi.py rang $SIM control gpol_noparang >> $SIM/arms.log 2>&1
for t in control feed0 revpsi; do
  for a in m90 feedms; do $L --slots 4 --mem 6 -- $PY $W/sim_chi.py casa $SIM $t $a >> $SIM/arms.log 2>&1; done
done
$L --slots 4 --mem 8 -- $PY $W/luno_rerun.py build $LUNO >> $LUNO/runner.log 2>&1
for a in m90 null; do $L --slots 8 --mem 12 -- $PY $W/luno_rerun.py rang $LUNO $a >> $LUNO/runner.log 2>&1; done
for a in m90 feed0; do $L --slots 4 --mem 12 -- $PY $W/luno_rerun.py casa $LUNO $a >> $LUNO/runner.log 2>&1; done
echo CHAIN DONE >> $LUNO/runner.log
