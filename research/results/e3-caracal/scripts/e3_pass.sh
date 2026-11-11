#!/bin/bash
# One E3 CARACal pass in WSL (research/e3-caracal.md section 4).
#   bash e3_pass.sh LEG PASS CONFIG RAWDIR      (PASS: correct | timed | smoke)
# Called under the heavy lock by the caller. Writes RUN=/mnt/d/rang/outputs/e3-20261111-LEG-PASS.
set -u
LEG=$1; PASS=$2; CFG=$3; RAW=$4
HERE=$(cd "$(dirname "$0")" && pwd)
RUN=/mnt/d/rang/outputs/e3-20261111-$LEG-$PASS
mkdir -p "$RUN"; cd "$RUN" || exit 2
cp "$CFG" config.yml
python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py status > lock-status-start.txt 2>&1
(cd "$RAW" && find . -maxdepth 3 -type f -printf '%P %s %T@\n' | sort) > raw-listing-before.txt
nproc > host.txt; free -b >> host.txt; uptime >> host.txt
LIM=""
[ "$PASS" = correct ] || [ "$PASS" = smoke ] && LIM="--limit-cpus 8 --limit-mem 30g"
rm -f .watch-stop
python3 "$HERE/e3_watch.py" watch.jsonl "$RUN" $LIM &
WPID=$!
sleep 2
echo "START $(date -Is)" > wall.txt
/usr/bin/time -v -o time-v.txt ~/Github/caracal/.venv/bin/caracal -c config.yml > caracal-stdout.log 2>&1
RC=$?
echo "END $(date -Is) rc=$RC" >> wall.txt
touch .watch-stop
wait $WPID
(cd "$RAW" && find . -maxdepth 3 -type f -printf '%P %s %T@\n' | sort) > raw-listing-after.txt
if cmp -s raw-listing-before.txt raw-listing-after.txt; then echo "raw unchanged" >> wall.txt; else echo "RAW CHANGED" >> wall.txt; fi
exit $RC
