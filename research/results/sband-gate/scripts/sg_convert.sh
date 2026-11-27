#!/bin/bash
# SPDX-License-Identifier: MIT
# S-band gate (research/sband-gate.md section 2): one half of one block as its
# own MS, by uhf-s-fetch's conversion (uhfs_convert.sh: E2-N's mvftoms call -f -a,
# rang's NATIVE_FLAGS, no --applycal, default --quack 1, the local RDB, no token,
# no network) with the frozen katdal scan list, then E2-N's prep step (token
# check, SIGMA_SPECTRUM removed, MS map, FLAG and FLAG_ROW hashes). Reads the
# MVF chunks and venv under ~/rang-data/uhf-s/ only; writes only under the run
# root. A shared heavy-lock job of 2 slots, 12 GB, nice 19 / ionice idle.
#   bash sg_convert.sh CBID HALF SCANS     (HALF: dev | heldout)
set -u
cb=$1; half=$2; scans=$3
S=$HOME/rang-data/uhf-s
V=$S/venv
RR=${RR:-$HOME/rang-data/outputs/sband-gate-20261127}
OUT=$RR/$cb/$half
REC=$OUT/receipts
MS=$OUT/$cb-$half.ms
LOCK=$HOME/Github/rang/tools/heavy_lock.py
mkdir -p "$REC"
RDB=$(ls "$S/mvf/$cb/"*.rdb | head -1)
step() { echo "$(date -u +%FT%TZ) $cb $half $1 $2 free $(df -BG --output=avail "$RR" | tail -1 | tr -d ' ')" | tee -a "$OUT/convert.log"; }
if [ ! -e "$REC/mvftoms.done" ]; then
  rm -rf "$MS"
  step mvftoms "start scans $scans"
  echo "$scans" > "$REC/mvftoms-scans.txt"
  python3 "$LOCK" run --slots 2 --mem 12 -- nice -n 19 ionice -c3 \
    /usr/bin/time -v -o "$REC/mvftoms.time" "$V/bin/python" "$V/bin/mvftoms.py" -f -a \
    --flags static,cam,data_lost,ingest_rfi,predicted_rfi --scans "$scans" -o "$MS" "$RDB" \
    > "$OUT/mvftoms.log" 2>&1
  rc=$?; step mvftoms "rc $rc"; [ $rc -eq 0 ] || exit $rc
  date -u +%FT%TZ > "$REC/mvftoms.done"
fi
if [ ! -e "$REC/prep.done" ]; then
  step prep start
  python3 "$LOCK" run --slots 1 --mem 8 -- nice -n 19 ionice -c3 \
    /usr/bin/time -v -o "$REC/prep.time" "$V/bin/python" "$S/scripts/uhfs_prep_ms.py" "$MS" "$REC" \
    > "$REC/prep.log" 2>&1
  rc=$?; step prep "rc $rc"; [ $rc -eq 0 ] || exit $rc
  date -u +%FT%TZ > "$REC/prep.done"
fi
du -sb "$MS" > "$REC/ms-bytes.txt"
grep -l -E "token=|eyJ[A-Za-z0-9._-]{20,}" "$OUT"/*.log "$REC"/* 2>/dev/null | sed 's/^/TOKEN FOUND IN: /' || true
step all done
