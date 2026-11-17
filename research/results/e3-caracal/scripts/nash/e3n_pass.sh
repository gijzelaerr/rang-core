#!/bin/bash
# One E3 CARACal pass on nash (research/e3-caracal.md 10.14), the apptainer form of e3_pass.sh.
#   bash e3n_pass.sh LEG PASS CONFIG RAWDIR CPULIST KILL_GIB
# Called under the heavy lock (nice 19 + ionice -c3 from RANG_HEAVY_NICE).
# Writes RUN=~/rang-data/outputs/e3-20261117-LEG-PASS. CPULIST pins the driver and every
# container (numactl --physcpubind); KILL_GIB is e3n_watch.py's tree-RSS guard.
set -u
LEG=$1; PASS=$2; CFG=$3; RAW=$4; CPUS=$5; KILL=$6
HERE=$(cd "$(dirname "$0")" && pwd)
RUN=~/rang-data/outputs/e3-20261117-$LEG-$PASS
SIF=~/rang-data/stimela-sif
CAR=~/Github/caracal/.venv/bin
mkdir -p "$RUN"; cd "$RUN" || exit 2
cp "$CFG" config.yml
python3 ~/Github/rang/tools/heavy_lock.py status > lock-status-start.txt 2>&1
(cd "$RAW" && find . -maxdepth 3 -type f -printf '%P %s %T@\n' | sort) > raw-listing-before.txt
{ hostname; nproc; free -b; uptime; numactl --hardware | head -3; echo "cpus $CPUS"; nice; ionice; } > host.txt
echo "START $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)" > wall.txt
"$CAR/python" "$HERE/e3n_watch.py" --log watch.jsonl --rundir "$RUN" --kill-gib "$KILL" -- \
  numactl --physcpubind="$CPUS" /usr/bin/time -v -o time-v.txt "$CAR/caracal" -c config.yml -sid "$SIF" \
  > caracal-stdout.log 2>&1
RC=$?
echo "END $(date -Is) rc=$RC load $(cut -d' ' -f1-3 /proc/loadavg)" >> wall.txt
(cd "$RAW" && find . -maxdepth 3 -type f -printf '%P %s %T@\n' | sort) > raw-listing-after.txt
if cmp -s raw-listing-before.txt raw-listing-after.txt; then echo "raw unchanged" >> wall.txt; else echo "RAW CHANGED" >> wall.txt; fi
exit $RC
