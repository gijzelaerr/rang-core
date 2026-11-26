#!/bin/bash
# SPDX-License-Identifier: MIT
# uhf-s-fetch driver (research/uhf-s-fetch.md section 3): for each block, in
# the order given, wait until the archive's object store lists its chunks
# (uhfs_stagecheck.py, every 30 min; on 2026-11-26 none of the four was
# staged), then fetch it as a shared heavy-lock job of 1 slot and 4 GB under
# nice -n 19 ionice -c3. A fetch that finds too many chunks missing (exit 3:
# staging still in progress) waits an hour and resumes; fetched chunks are kept.
# After a block's fetch.done its conversion starts (uhfs_convert.sh: its own
# lock jobs, one block at a time through flock) and the next block's fetch.
# Stops at the links' expiry. Writes a status file STATUS (default
# ~/rang-data/uhf-s/status.md), under 15 lines, at every step.
#   setsid nohup bash uhfs_fetch_all.sh CBID [CBID ...] > logs/fetch-all.log 2>&1 < /dev/null &
# WORKERS and MBPS set the fetch's worker count and global rate cap (MB/s).
set -u
R=$HOME/rang-data/uhf-s
V=$HOME/Build/tmp/20261126-uhf-s/venv
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
staged() {  # the block's visibility and flag buckets both list objects
  "$V/bin/python" "$R/scripts/uhfs_stagecheck.py" "$R/sarao-links.txt" "$R/logs/stagecheck.jsonl" > /dev/null 2>&1
  tail -4 "$R/logs/stagecheck.jsonl" | python3 -c "
import json, sys
for l in sys.stdin:
    d = json.loads(l)
    if d['cbid'] == '$1':
        sys.exit(0 if d['vis']['keys_listed'] and d['flags']['keys_listed'] else 1)
sys.exit(1)"
}
for cb in "$@"; do
  need=$(python3 -c "import json;print(int(json.load(open('$R/meta/$cb.json'))['vis_bytes_cross_all']*3.3/2**30))")
  attempt=0
  while [ ! -e "$R/mvf/$cb-receipts/fetch.done" ]; do
    if [[ "$(date -u +%F)" > "$EXPIRY" ]]; then echo "$(now) links expired, stop"; status "$@"; exit 4; fi
    status "$@"
    if ! staged "$cb"; then echo "$(now) $cb not staged"; sleep 1800; continue; fi
    free=$(df -BG --output=avail "$R" | tail -1 | tr -dc 0-9)
    if [ $((free - need)) -lt $FLOOR_GB ]; then echo "$(now) $cb: disk rule not met (free $free need $need), wait"; sleep 3600; continue; fi
    attempt=$((attempt + 1))
    echo "$(now) $cb fetch attempt $attempt (free $free GiB, need $need)"
    /usr/bin/time -v -o "$R/logs/fetch-$cb-$attempt.time" \
      python3 "$LOCK" run --slots 1 --mem 4 -- nice -n 19 ionice -c3 \
      "$V/bin/python" "$R/scripts/uhfs_fetch.py" "$R/sarao-links.txt" "$R/mvf" \
      --cbid "$cb" --workers "$WORKERS" --max-mbps "$MBPS" >> "$R/logs/fetch-$cb.log" 2>&1
    rc=$?
    echo "$(now) $cb fetch attempt $attempt rc $rc"
    [ -e "$R/mvf/$cb-receipts/fetch.done" ] || sleep 3600
  done
  status "$@"
  if [ ! -e "$R/mvf/$cb-receipts/ms-sha256.done" ]; then
    setsid nohup bash "$R/scripts/uhfs_convert.sh" "$cb" >> "$R/logs/convert-$cb.log" 2>&1 < /dev/null &
  fi
done
echo "$(now) all fetches ended"
while pgrep -f "uhfs_convert.sh" > /dev/null; do status "$@"; sleep 1800; done
status "$@"
