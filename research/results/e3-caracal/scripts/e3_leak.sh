#!/bin/bash
# E3-B 1934-638 leakage images (research/e3-caracal.md section 5), WSL side:
#   bash e3_leak.sh SPLIT.ms FIELD OUTDIR [THREADS]
# WSClean 3.7 (rang-wsclean-native:3.7) on CARACal's CORRECTED_DATA with
# E2-B's image settings (e2b.yaml: 2048 x 2", Briggs 0, 8 joined channels,
# IQUV joined, mgain 0.9) and A0 rule 6 (auto-mask 5 sigma, clean to 3 sigma).
# Not CARACal's step; outside its wall time. Call under the heavy lock.
set -eu
MS=$(readlink -f "$1"); FIELD=$2; OUT=$3; J=${4:-8}
mkdir -p "$OUT"
FID=$(~/Github/caracal/.venv/bin/python -c "
from casacore.tables import table; import sys
n=list(table('$MS/FIELD',ack=False).getcol('NAME')); print(n.index('$FIELD'))")
D=$(dirname "$MS"); B=$(basename "$MS")
/usr/bin/time -v -o "$OUT/time-v.txt" docker run --rm --user "$(id -u):$(id -g)" \
  -v "$D:/data" -v "$(readlink -f "$OUT"):/run" -w /run rang-wsclean-native:3.7 \
  wsclean -name leak -field "$FID" -data-column CORRECTED_DATA \
    -size 2048 2048 -scale 2asec -weight briggs 0 \
    -channels-out 8 -join-channels -pol IQUV -join-polarizations \
    -mgain 0.9 -niter 1000000 -auto-mask 5 -auto-threshold 3 -j "$J" \
    "/data/$B" > "$OUT/wsclean.log" 2>&1
echo "field $FIELD id $FID done"
