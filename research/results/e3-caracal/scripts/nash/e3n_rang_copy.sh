#!/bin/bash
# Copy E3-A's verified e2a.ms for rang's E2-A timed run on nash and hash its FLAG
# (research/e3-caracal.md 10.14). Run under nice -n 19 ionice -c3.
#   bash e3n_rang_copy.sh SRC_MS OUTDIR
set -u
SRC=$1; O=$2; L=$O/e2a-run.log
mkdir -p "$O"
echo "COPY START $(date -Is)" >> $L
python3 ~/Github/rang/tools/heavy_lock.py run --slots 1 --mem 2 -- /usr/bin/time -f "wall %e s" cp -a "$SRC" "$O/e2a.ms" >> $L 2>&1
echo "COPY END $(date -Is) rc $?" >> $L
~/Github/rang/.venv/bin/python ~/Github/rang/research/results/e2-acceptance-scripts/e2_flaghash.py "$O/e2a.ms" "$O/flaghash-copy.json" >> $L 2>&1
echo "HASH END $(date -Is) rc $?" >> $L
