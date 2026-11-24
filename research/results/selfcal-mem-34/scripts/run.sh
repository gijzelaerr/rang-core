#!/bin/bash
# selfcal-mem-34 on nash (research/selfcal-mem-34.md). Usage: run.sh STEP [TAG SIZE]
set -euo pipefail
source ~/.rang-env.sh
W=~/Worktrees/rang/selfcal-mem-34
PY=$W/.venv/bin/python
LOCK="$HOME/Github/rang/.venv/bin/python $HOME/Github/rang/tools/heavy_lock.py"
O=~/rang-data/outputs/selfcal-mem-34-20261124
export RANG_FLOOR_HELD=$O/inputs/real
export PATH=$W/.venv/bin:$PATH
cd $W
stamp() { echo "== $(date -u +%FT%TZ) load $(cut -d" " -f1-3 /proc/loadavg) $*"; }
case $1 in
  base)
    $LOCK run --slots 1 --mem 4 -- nice -n 19 ionice -c3 bash -c "/usr/bin/time -f \"base %e s %M KB\" $PY examples/selfcal_grid.py base --out $O && /usr/bin/time -f \"prepare %e s %M KB\" $PY examples/selfcal_grid.py prepare D --out $O" ;;
  pipeline) # TAG SIZE
    T=$2; S=${3:-4096}; R=$O/$T
    [ -e $R/run ] && { echo "$R/run exists"; exit 1; }
    mkdir -p $R
    grep -v "memory_limit_gb" $O/D/config.yaml | sed "/^data:\$/d" | sed "s/^  - 4096\$/  - $S/" > $R/config.yaml
    $PY - $R/config.yaml <<PYEOF
import sys, yaml
p = sys.argv[1]; c = yaml.safe_load(open(p))
c["image"]["extra_args"] = ["-memory-report"]
yaml.safe_dump(c, open(p, "w"), sort_keys=False)
PYEOF
    $LOCK run --slots 8 --mem 16 -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=8 bash -c "$(declare -f stamp); stamp $T start; /usr/bin/time -f \"selfcal %e s %M KB\" rang-core selfcal $R/config.yaml $O/D/pilot.ms --run-dir $R/run; stamp $T end" ;;
  *) echo "unknown step $1"; exit 2 ;;
esac
