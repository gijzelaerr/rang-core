#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-s-fetch smoke (research/uhf-s-fetch.md section 3): one scan of one block
# through fetch, mvftoms and prep, to size rate, wall, memory, CPU and MS bytes
# before the full fetch. The smoke MS is deleted afterwards; its chunks stay in
# mvf/ and are reused by the full fetch.
#   setsid nohup bash uhfs_smoke.sh CBID SCAN > logs/smoke.log 2>&1 &
set -u
cb=$1; scan=$2
R=$HOME/rang-data/uhf-s
V=$HOME/rang-data/uhf-s/venv
LOCK=$HOME/Github/rang/tools/heavy_lock.py
SM=$R/smoke
mkdir -p "$SM" "$R/mvf"
echo "$(date -u +%FT%TZ) fetch start"
python3 "$LOCK" run --slots 1 --mem 4 -- nice -n 19 ionice -c3 /usr/bin/time -v -o "$SM/fetch.time" \
  "$V/bin/python" "$R/scripts/uhfs_fetch.py" "$R/sarao-links.txt" "$R/mvf" --cbid "$cb" --scans "$scan" \
  --workers "${WORKERS:-6}" --max-mbps "${MBPS:-40}"
echo "$(date -u +%FT%TZ) fetch rc $?"
RDB=$(ls "$R/mvf/$cb/"*.rdb | head -1)
python3 "$LOCK" run --slots 4 --mem 32 -- nice -n 19 ionice -c3 /usr/bin/time -v -o "$SM/mvftoms.time" \
  "$V/bin/python" "$V/bin/mvftoms.py" -f -a --flags static,cam,data_lost,ingest_rfi,predicted_rfi \
  --scans "$scan" -o "$SM/$cb-scan$scan.ms" "$RDB" > "$SM/$cb-scan$scan-mvftoms.log" 2>&1
echo "$(date -u +%FT%TZ) mvftoms rc $?"
du -sb "$SM/$cb-scan$scan.ms" "$SM/$cb-scan$scan.ms"/table.f* > "$SM/ms-bytes.txt"
python3 "$LOCK" run --slots 1 --mem 8 -- nice -n 19 ionice -c3 /usr/bin/time -v -o "$SM/prep.time" \
  "$V/bin/python" "$R/scripts/uhfs_prep_ms.py" "$SM/$cb-scan$scan.ms" "$SM/prep" > "$SM/prep.log" 2>&1
echo "$(date -u +%FT%TZ) prep rc $?"
du -sb "$SM/$cb-scan$scan.ms" >> "$SM/ms-bytes.txt"
grep -c -E "token=|eyJ[A-Za-z0-9._-]{20,}" "$SM"/*.log "$SM"/*.time "$R/mvf/$cb-receipts-scans-$scan"/* | sed 's/^/token count /'
rm -rf "$SM/$cb-scan$scan.ms"
echo "$(date -u +%FT%TZ) smoke done"
