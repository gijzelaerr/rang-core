#!/bin/bash
# floor-4 and selfcal-defaults on nash: one lock job per step, every one under nice 19 (the lock's
# RANG_HEAVY_NICE=19 and this script's own prefix). Usage: run_nash.sh STEP [RUN]
set -euo pipefail
source ~/.rang-env.sh
W=~/Worktrees/rang/floor-4
PY=~/Github/rang/.venv/bin/python
LOCK="$PY $HOME/Github/rang/tools/heavy_lock.py"
O=~/rang-data/outputs
F4=$O/floor-4-20261117
G=$O/selfcal-defaults-20261117
export RANG_FLOOR_HELD=$O/20261103-gemclean-heldout/real
export RAYON_NUM_THREADS=8
export PATH=$HOME/Github/rang/.venv/bin:$PATH
LOG=~/Build/tmp/20261117-floor4/logs
mkdir -p "$LOG" "$F4" "$G"
cd "$W"
step=$1
run=${2:-}
stamp() { echo "== $(date -u +%FT%TZ) load $(cut -d' ' -f1-3 /proc/loadavg) $*"; }
case $step in
  g1)
    $LOCK run --slots 8 --mem 20 -- bash -c "
      set -e
      $(declare -f stamp)
      stamp g1 start
      /usr/bin/time -f 'copy %e s %M KB' $PY examples/selfcal_grid.py f3 copy P --out $F4/g1
      /usr/bin/time -f 'g0 %e s %M KB' $PY examples/selfcal_grid.py f3 g0 --out $F4/g1
      /usr/bin/time -f 'selfcal %e s %M KB' rang-core selfcal research/results/floor-3/p1.yaml $F4/g1/P/pilot.ms --run-dir $F4/g1/P/run
      /usr/bin/time -f 'score %e s %M KB' $PY examples/selfcal_grid.py f3 score P --out $F4/g1
      $PY examples/selfcal_grid.py f3 summary --out $F4/g1
      $PY examples/selfcal_grid.py f3 clean P --out $F4/g1
      stamp g1 end" ;;
  sim)
    $LOCK run --slots 8 --mem 24 -- bash -c "
      set -e
      $(declare -f stamp)
      stamp sim start
      /usr/bin/time -f 'sim %e s %M KB' $PY examples/floor4_tests.py sim --out $F4/floor-4
      stamp sim end" ;;
  x)
    $LOCK run --slots 4 --mem 16 -- bash -c "
      set -e
      $(declare -f stamp)
      stamp x start
      /usr/bin/time -f 'x %e s %M KB' $PY examples/floor4_tests.py x --out $F4/floor-4 --g1 $F4/g1
      $PY examples/floor4_tests.py summary --out $F4/floor-4 --g1 $F4/g1
      stamp x end" ;;
  sets)
    $LOCK run --slots 4 --mem 16 -- bash -c "
      set -e
      $(declare -f stamp)
      stamp sets start
      /usr/bin/time -f 'base %e s %M KB' $PY examples/selfcal_grid.py base --out $G
      /usr/bin/time -f 'sets %e s %M KB' $PY examples/selfcal_grid.py sets --out $G
      stamp sets end" ;;
  grid)
    extra=""
    [ "$run" = X ] && extra="--minuvw 400"
    $LOCK run --slots 8 --mem ${GRIDMEM:-20} -- bash -c "
      set -e
      $(declare -f stamp)
      stamp $run start
      /usr/bin/time -f 'prepare %e s %M KB' $PY examples/selfcal_grid.py prepare $run --out $G $extra
      /usr/bin/time -f 'selfcal %e s %M KB' rang-core selfcal $G/$run/config.yaml $G/$run/pilot.ms --run-dir $G/$run/run
      $PY examples/selfcal_grid.py clean $run --out $G
      [ \"${NOSCORE:-}\" = 1 ] || /usr/bin/time -f 'score %e s %M KB' $PY examples/selfcal_grid.py score $run --out $G
      stamp $run end" ;;
  score)
    $LOCK run --slots 4 --mem 16 -- bash -c "
      set -e
      /usr/bin/time -f 'score %e s %M KB' $PY examples/selfcal_grid.py score $run --out $G" ;;
  *) echo "unknown step $step"; exit 2 ;;
esac
