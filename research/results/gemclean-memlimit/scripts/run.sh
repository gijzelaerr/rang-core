#!/bin/bash
# SPDX-License-Identifier: MIT
# gemclean-memlimit on glacier (research/gemclean-memlimit.md). Usage: run.sh STEP [ARGS]
#   base              the four-correlation pilot copy, once (selfcal_grid.py base) into $O/base
#   prepare TAG       $O/TAG/pilot.ms from the base, the 128 held-out channels flagged (selfcal_grid.py prepare D)
#   pipeline TAG [LIMIT]   rang-core selfcal with D's config, -memory-report; LIMIT sets data.memory_limit_gb
#   image TAG MS SIZE [EXTRA...]   one standalone gemclean image (the selfcal round-1 argv) of MS at SIZE
set -euo pipefail
W=/c/Users/gijsm/Worktrees/rang/gemclean-memlimit
PY=$W/.venv/Scripts/python.exe
LOCK="python /c/Users/gijsm/Github/rang/tools/heavy_lock.py"
O=/d/rang/outputs/20261128-gemclean-memlimit
export RANG_FLOOR_HELD=D:/rang/outputs/20261103-gemclean-heldout/real
cd $W
stamp() { echo "== $(date -u +%FT%TZ) $*"; }
case $1 in
  base)
    $LOCK run --slots 1 --mem 4 -- $PY examples/selfcal_grid.py base --out D:/rang/outputs/20261128-gemclean-memlimit ;;
  prepare) # TAG
    T=$2; mkdir -p $O/$T
    $LOCK run --slots 1 --mem 4 -- $PY examples/selfcal_grid.py prepare D --out D:/rang/outputs/20261128-gemclean-memlimit
    mv $O/D/pilot.ms $O/$T/pilot.ms; mv $O/D/holdout.json $O/$T/; cp $O/D/config.yaml $O/$T/config-D.yaml ;;
  pipeline) # TAG [LIMIT]
    T=$2; L=${3:-}; R=$O/$T
    [ -e $R/run ] && { echo "$R/run exists"; exit 1; }
    $PY - $R/config-D.yaml $R/config.yaml "$L" <<PYEOF
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
c["data"].pop("memory_limit_gb", None)
if not c["data"]:
    del c["data"]
if sys.argv[3]:
    c.setdefault("data", {})["memory_limit_gb"] = float(sys.argv[3])
c["image"]["extra_args"] = ["-memory-report"]
yaml.safe_dump(c, open(sys.argv[2], "w"), sort_keys=False)
PYEOF
    $LOCK run --slots 8 --mem 16 -- env RAYON_NUM_THREADS=8 bash -c "$(declare -f stamp); stamp $T start; $PY $W/research/results/gemclean-memlimit/scripts/peak.py $W/.venv/Scripts/rang-core.exe selfcal $R/config.yaml $R/pilot.ms --run-dir $R/run; stamp $T end" ;;
  image) # TAG MS SIZE ACC ext|bin [EXTRA...]: the selfcal round-1 argv of D's config on MS
    T=$2; MS=$3; S=$4; A=$5; K=$6; shift 6; R=$O/img/$T
    [ -e $R ] && { echo "$R exists"; exit 1; }
    mkdir -p $R
    if [ $K = bin ]; then G=$W/core/target/release/gemclean.exe; else G="$PY -m rang.gemclean"; fi
    $LOCK run --slots 8 --mem 16 -- env RAYON_NUM_THREADS=8 RANG_PEAK_JSON=$(cygpath -m $R/peak.json) bash -c "$(declare -f stamp); stamp $T start; $PY $W/research/results/gemclean-memlimit/scripts/peak.py $G -name $(cygpath -m $R/image) -size $S $S -scale 3asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -threshold 0.003 -j 8 -wgridder-accuracy $A -data-column DATA -field 0 -no-update-model-required -memory-report $* $(cygpath -m $MS) > $R/gemclean.log 2>&1; echo exit \$?; stamp $T end" ;;
  *) echo "unknown step $1"; exit 2 ;;
esac
