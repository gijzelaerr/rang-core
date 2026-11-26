#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-s-fetch conversion of one fetched block (research/uhf-s-fetch.md section 3):
# E2-N's mvftoms call (-f -a, rang's NATIVE_FLAGS, no --applycal, default
# --quack 1) on the local RDB, no token, no network; then E2-N's prep step
# (token check, SIGMA_SPECTRUM removed, MS map, FLAG and FLAG_ROW hashes) and a
# SHA-256 of every file of the MS. One block at a time (flock); each step a
# shared heavy-lock job under nice -n 19 ionice -c3.
#   bash uhfs_convert.sh CBID
set -u
cb=$1
R=$HOME/rang-data/uhf-s
V=$HOME/Build/tmp/20261126-uhf-s/venv
LOCK=$HOME/Github/rang/tools/heavy_lock.py
REC=$R/mvf/$cb-receipts
MS=$R/ms/$cb.ms
mkdir -p "$R/ms"
exec 9> "$R/convert.lock"
flock 9
RDB=$(ls "$R/mvf/$cb/"*.rdb | head -1)
step() { echo "$(date -u +%FT%TZ) $cb $1 $2 free $(df -BG --output=avail "$R" | tail -1 | tr -d ' ')"; }
if [ ! -e "$REC/mvftoms.done" ]; then
  rm -rf "$MS"
  step mvftoms start
  python3 "$LOCK" run --slots 4 --mem 32 -- nice -n 19 ionice -c3 \
    /usr/bin/time -v -o "$REC/mvftoms.time" "$V/bin/python" "$V/bin/mvftoms.py" -f -a \
    --flags static,cam,data_lost,ingest_rfi,predicted_rfi -o "$MS" "$RDB" > "$R/ms/$cb-mvftoms.log" 2>&1
  rc=$?
  step mvftoms "rc $rc"
  [ $rc -eq 0 ] || exit $rc
  date -u +%FT%TZ > "$REC/mvftoms.done"
fi
if [ ! -e "$REC/prep.done" ]; then
  step prep start
  python3 "$LOCK" run --slots 1 --mem 8 -- nice -n 19 ionice -c3 \
    /usr/bin/time -v -o "$REC/prep.time" "$V/bin/python" "$R/scripts/uhfs_prep_ms.py" "$MS" "$REC" > "$REC/prep.log" 2>&1
  rc=$?
  step prep "rc $rc"
  [ $rc -eq 0 ] || exit $rc
  date -u +%FT%TZ > "$REC/prep.done"
fi
if [ ! -e "$REC/ms-sha256.done" ]; then
  step ms-sha256 start
  python3 "$LOCK" run --slots 1 --mem 2 -- nice -n 19 ionice -c3 /usr/bin/time -v -o "$REC/ms-sha256.time" \
    bash -c "cd '$R/ms' && find '$cb.ms' -type f | LC_ALL=C sort | xargs -d '\n' sha256sum > '$REC/ms-sha256.txt'"
  rc=$?
  step ms-sha256 "rc $rc"
  [ $rc -eq 0 ] || exit $rc
  date -u +%FT%TZ > "$REC/ms-sha256.done"
fi
du -sb "$MS" > "$REC/ms-bytes.txt"
grep -l -E "token=|eyJ[A-Za-z0-9._-]{20,}" "$R"/logs/* "$REC"/* "$R/ms/$cb-mvftoms.log" 2>/dev/null | sed 's/^/TOKEN FOUND IN: /' || true
step all done
