#!/bin/bash
# Verify and hash an already built e2a.ms on nash (the second half of e3n_build.sh).
#   bash e3n_verify.sh OUTDIR [--rows N]
set -u
O=$1; shift
D=~/rang-data/e2-a/ESO137
R=~/Github/rang
PY=$R/.venv/bin/python
S=$R/research/results/e2-acceptance-scripts
LOCK=$R/tools/heavy_lock.py
G="$D/ms1_primary.zarr:MAIN_4 $D/ms1_target.zarr:MAIN_4 $D/ms1_primary.zarr:MAIN_5"
cd "$R" || exit 2
echo "blob $(git hash-object $S/e2_convert.py) main $(git rev-parse --short HEAD)"
t1=$(date +%s); echo "START $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
nice -n 19 ionice -c3 python3 $LOCK run --slots 1 --mem 3 -- /usr/bin/time -f "wall %e s rss %M KB" \
  "$PY" $S/e2_convert.py verify "$O/e2a.ms" $G "$@" --json "$O/verify.json"; rc=$?
t2=$(date +%s); echo "VERIFY rc=$rc wall=$((t2-t1)) s"
[ $rc -eq 0 ] || exit $rc
nice -n 19 ionice -c3 python3 $LOCK run --slots 1 --mem 3 -- \
  "$PY" $S/e2_flaghash.py "$O/e2a.ms" "$O/flaghash.json"; rc=$?
t3=$(date +%s); echo "HASH rc=$rc wall=$((t3-t2)) s END $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
cat "$O/flaghash.json"
exit $rc
