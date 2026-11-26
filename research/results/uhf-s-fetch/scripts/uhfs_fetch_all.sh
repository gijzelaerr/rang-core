#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-s-fetch driver (research/uhf-s-fetch.md section 3): every 30 min, list
# the archive's object store (uhfs_stagecheck.py; on 2026-11-26 none of the four
# blocks was staged) and fetch the first block, in the order given, that is
# staged and not yet fetched, as a shared heavy-lock job of 1 slot and 4 GB
# under nice -n 19 ionice -c3. A fetch that ends with chunks missing (exit 3:
# staging still in progress, or lost chunks awaiting confirmation an hour
# later) is retried on a later pass; fetched chunks are kept. After a block's
# fetch.done its conversion starts (uhfs_convert.sh with the block's scan
# selection from SELECTION below: its own lock jobs, one block at a time).
# Stops at the links' expiry. Writes a status file STATUS (default
# ~/rang-data/uhf-s/status.md), under 15 lines, at every step.
#   setsid nohup bash uhfs_fetch_all.sh CBID [CBID ...] > logs/fetch-all.log 2>&1 < /dev/null &
# WORKERS and MBPS set the fetch's worker count and global rate cap (MB/s).
set -u
R=$HOME/rang-data/uhf-s
V=$R/venv
LOCK=$HOME/Github/rang/tools/heavy_lock.py
WORKERS=${WORKERS:-6}
MBPS=${MBPS:-40}
FLOOR_GB=2048
EXPIRY=${EXPIRY:-2027-01-24}
STATUS=${STATUS:-$R/status.md}
mkdir -p "$R/mvf" "$R/logs"
now() { date -u +%FT%TZ; }
status() {
  {
    echo "# uhf-s-fetch on nash ($(now))"
    echo "- driver pid $$, blocks: $*"
    for c in $ALL; do
      s="waiting for staging"
      f=$R/mvf/$c-receipts/fetch-progress.jsonl
      [ -e "$f" ] && s="fetch: $(python3 -c 'import json,sys;d=json.loads(open(sys.argv[1]).readlines()[-1]);print("%d/%d chunks, %s MB/s, lost %d" % (d["chunks_done"],d["chunks_total"],d["mb_per_s"],d["lost"]))' "$f")"
      [ -e "$R/mvf/$c-receipts/fetch.done" ] && s="fetched"
      [ -e "$R/mvf/$c-receipts/mvftoms.done" ] && s="converted"
      [ -e "$R/mvf/$c-receipts/ms-sha256.done" ] && s="converted, prepped, hashed"
      echo "- $c: $s"
    done
    echo "- free: $(df -BG --output=avail "$R" | tail -1 | tr -d ' ')"
    echo "- last stage check: $(tail -1 "$R/logs/stagecheck.jsonl" 2>/dev/null | cut -c1-160)"
  } > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}
ALL="$*"
# conversion selections, katdal track scans (uhf-gate.md section 2, amendments 1 and 2):
# the UHF gate's selection; the S-band blocks whole (empty). FETCH: the scans
# fetched (UHF: the selection plus the reserve; empty: every track scan).
declare -A FETCH=(
  [1752418159]="1,3,15,17,19,31,33,35,37,39"
  [1726220298]="0,2,4,8,12,16,20,22,24,26,28,30,32,34,36,38,40,42,44,46,50,54,58,60"
)
declare -A SELECTION=(
  [1752418159]="1,3,15,17,19,31,33,35,37,39"
  [1726220298]="0,2,4,8,12,16,20,22,24,26,28,30,32,34,36,38,42,46,50,54,58,60"
  [1747682474]=""
  [1680455600]=""
  [1740534088]="2,4,8,12,14,16,18,20,22,24,28,32,34"
  [1737424638]="0,2,6,10,12,14,16,18,20,22,23,25,27,31,35,37"
  [1729932377]=""
  [1690097605]=""
)
staged() {  # in the latest stage check, the block's visibility and flag buckets both list objects
  tail -n 32 "$R/logs/stagecheck.jsonl" | python3 -c "
import json, sys
ok = False
for l in sys.stdin:
    d = json.loads(l)
    if d['cbid'] == '$1':
        ok = bool(d['vis']['keys_listed'] and d['flags']['keys_listed'])
sys.exit(0 if ok else 1)"
}
# catch-up after a restart: a fetched block whose conversion is not done
for cb in "$@"; do
  if [ -e "$R/mvf/$cb-receipts/fetch.done" ] && [ ! -e "$R/mvf/$cb-receipts/ms-sha256.done" ]; then
    SCANS="${SELECTION[$cb]}" setsid nohup bash "$R/scripts/uhfs_convert.sh" "$cb"       >> "$R/logs/convert-$cb.log" 2>&1 < /dev/null &
  fi
done
declare -A ATTEMPT=()
while :; do
  if [[ "$(date -u +%F)" > "$EXPIRY" ]]; then echo "$(now) links expired, stop"; status "$@"; exit 4; fi
  status "$@"
  "$V/bin/python" "$R/scripts/uhfs_stagecheck.py" "$R/sarao-links.txt" "$R/logs/stagecheck.jsonl" > /dev/null 2>&1
  left=0; picked=""
  for cb in "$@"; do
    [ -e "$R/mvf/$cb-receipts/fetch.done" ] && continue
    left=$((left + 1))
    if [ -z "$picked" ] && staged "$cb"; then picked=$cb; fi
  done
  [ $left -eq 0 ] && break
  if [ -z "$picked" ]; then echo "$(now) none staged of $left left"; sleep 1800; continue; fi
  cb=$picked
  need=$(python3 -c "import json;print(int(json.load(open('$R/meta/$cb.json'))['vis_bytes_cross_all']*3.3/2**30))")
  free=$(df -BG --output=avail "$R" | tail -1 | tr -dc 0-9)
  if [ $((free - need)) -lt $FLOOR_GB ]; then echo "$(now) $cb: disk rule not met (free $free need $need), wait"; sleep 3600; continue; fi
  ATTEMPT[$cb]=$(( ${ATTEMPT[$cb]:-0} + 1 ))
  n=${ATTEMPT[$cb]}
  echo "$(now) $cb fetch attempt $n (free $free GiB, need $need)"
  /usr/bin/time -v -o "$R/logs/fetch-$cb-$n.time"     python3 "$LOCK" run --slots 1 --mem 4 -- nice -n 19 ionice -c3     "$V/bin/python" "$R/scripts/uhfs_fetch.py" "$R/sarao-links.txt" "$R/mvf"     --cbid "$cb" --workers "$WORKERS" --max-mbps "$MBPS" ${FETCH[$cb]:+--scans ${FETCH[$cb]//,/ }}     >> "$R/logs/fetch-$cb.log" 2>&1
  rc=$?
  echo "$(now) $cb fetch attempt $n rc $rc"
  if [ -e "$R/mvf/$cb-receipts/fetch.done" ]; then
    if [ ! -e "$R/mvf/$cb-receipts/ms-sha256.done" ]; then
      SCANS="${SELECTION[$cb]}" setsid nohup bash "$R/scripts/uhfs_convert.sh" "$cb"         >> "$R/logs/convert-$cb.log" 2>&1 < /dev/null &
    fi
  else
    sleep 1800
  fi
done
echo "$(now) all fetches ended"
while pgrep -f "uhfs_convert.sh" > /dev/null; do status "$@"; sleep 1800; done
status "$@"
