#!/bin/bash
# selfcal-memory measurements on nash (research/selfcal-memory.md). Usage: run.sh STEP
set -euo pipefail
source ~/.rang-env.sh
W=~/Worktrees/rang/selfcal-memory
PY=$W/.venv/bin/python
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
O=~/rang-data/outputs/selfcal-memory-20261117
MS=$O/D/pilot.ms
S=$O/solves
mkdir -p $S
export PATH=$W/.venv/bin:$PATH
cd $W
stamp() { echo "== $(date -u +%FT%TZ) load $(cut -d" " -f1-3 /proc/loadavg) $*"; }
solve() { # name slots mem args...
  local name=$1 slots=$2 mem=$3; shift 3
  $LOCK run --slots $slots --mem $mem -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=$slots bash -c "$(declare -f stamp); stamp $name start; /usr/bin/time -f \"$name %e s %M KB\" $PY examples/selfcal_memory.py solve $MS $* --out $S/$name.npz; stamp $name end"
}
case $1 in
  pipeline)
    grep -v "memory_limit_gb" $O/D/config.yaml | sed "/^data:\$/d" > $O/D/config-default.yaml
    $LOCK run --slots 8 --mem 16 -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=8 bash -c "$(declare -f stamp); stamp pipeline start; /usr/bin/time -f \"selfcal %e s %M KB\" rang-core selfcal $O/D/config-default.yaml $MS --run-dir $O/D/run; stamp pipeline end" ;;
  sp-stream) solve sp-stream 2 10 --type Sp --solint inf --limit 8 --stream auto ;;
  sa-stream) solve sa-stream 2 10 --type Sa --solint inf --limit 8 --stream auto ;;
  sp-whole) solve sp-whole 2 48 --type Sp --solint inf --limit 96 --stream false ;;
  sa-whole) solve sa-whole 2 48 --type Sa --solint inf --limit 96 --stream false ;;
  sp-600) solve sp-600 2 18 --type Sp --solint 600s --limit 16 --stream false ;;
  sp-300) solve sp-300 2 14 --type Sp --solint 300s --limit 12 --stream false ;;
  *) echo "unknown step $1"; exit 2 ;;
esac
