#!/bin/bash
# Build and verify E3-A's e2a.ms on nash with E2's converter (blob e33bbe4b in ~/Github/rang),
# then hash FLAG and FLAG_ROW (research/e3-caracal.md 10.14), under the shared heavy lock.
#   bash e3n_build.sh OUTDIR [--rows N]
# Groups as section 2 and e2-acceptance 9.1: ms1_primary MAIN_4, ms1_target MAIN_4, ms1_primary MAIN_5.
set -u
O=$1; shift
D=~/rang-data/e2-a/ESO137
R=~/Github/rang
PY=$R/.venv/bin/python
S=$R/research/results/e2-acceptance-scripts
LOCK=$R/tools/heavy_lock.py
G="$D/ms1_primary.zarr:MAIN_4 $D/ms1_target.zarr:MAIN_4 $D/ms1_primary.zarr:MAIN_5"
mkdir -p "$O"; cd "$R" || exit 2
echo "blob $(git hash-object $S/e2_convert.py) main $(git rev-parse --short HEAD)"
echo "START $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
t0=$(date +%s)
nice -n 19 ionice -c3 python3 $LOCK run --slots 1 --mem 3 -- /usr/bin/time -f "wall %e s rss %M KB" \
  "$PY" $S/e2_convert.py build "$O/e2a.ms" $G "$@"; rc=$?
t1=$(date +%s); echo "BUILD rc=$rc wall=$((t1-t0)) s"
[ $rc -eq 0 ] || exit $rc
nice -n 19 ionice -c3 python3 $LOCK run --slots 1 --mem 3 -- /usr/bin/time -f "wall %e s rss %M KB" \
  "$PY" $S/e2_convert.py verify "$O/e2a.ms" $G "$@" --json "$O/verify.json"; rc=$?
t2=$(date +%s); echo "VERIFY rc=$rc wall=$((t2-t1)) s"
[ $rc -eq 0 ] || exit $rc
nice -n 19 ionice -c3 python3 $LOCK run --slots 1 --mem 3 -- \
  "$PY" $S/e2_flaghash.py "$O/e2a.ms" "$O/flaghash.json"; rc=$?
t3=$(date +%s); echo "HASH rc=$rc wall=$((t3-t2)) s END $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
cat "$O/flaghash.json"
exit $rc
