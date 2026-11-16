#!/bin/bash
# E2-N conversion (research/e2n-native.md section 4), WSL. katdal's mvftoms.py
# on the local MVF copy: no token, no network. Full polarisation (-f), no
# autocorrelations (-a), no calibration applied (no --applycal), rang's
# NATIVE_FLAGS only, mvftoms's default --quack 1.
#   bash e2n_tomss.sh OUT.ms SCANS        (SCANS: katdal indices, comma list)
set -u
OUT=$1
SCANS=$2
V=~/Build/tmp/20261116-e2n/venv
# RDB: the local MVF copy (Windows WSL default; on nash ~/rang-data/outputs/e2n-20261116/mvf/...)
RDB=${RDB:-/mnt/d/rang/outputs/e2n-20261116/mvf/1735268787/1735268787_sdp_l0.full.rdb}
# PREFIX: nash's owner rule, nice -n 19 ionice -c3 (empty on the Windows host)
PREFIX=${PREFIX:-}
LOG=${OUT%.ms}-mvftoms.log
echo "START $(date -u +%FT%TZ) $OUT scans $SCANS free $(df -BG --output=avail "$(dirname "$OUT")" | tail -1)" >> "$LOG"
$PREFIX /usr/bin/time -v "$V/bin/python" "$V/bin/mvftoms.py" -f -a \
  --flags static,cam,data_lost,ingest_rfi,predicted_rfi \
  --scans "$SCANS" -o "$OUT" "$RDB" >> "$LOG" 2>&1
rc=$?
echo "END $(date -u +%FT%TZ) rc $rc free $(df -BG --output=avail "$(dirname "$OUT")" | tail -1)" >> "$LOG"
grep -c "token=" "$LOG" | sed 's/^/token lines in log: /' >> "$LOG"
exit $rc
