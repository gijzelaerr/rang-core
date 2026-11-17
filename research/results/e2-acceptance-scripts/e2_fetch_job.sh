#!/bin/sh
# e2_fetch_job.sh LEG: run e2_fetch.py for LEG into D:\rang\data\e2-LEG, logging START/END/rc.
leg=$1; out=/d/rang/data/e2-$leg; log=/d/rang/data/e2-$leg.log
mkdir -p "$out"
echo "START $(date '+%F %T') free=$(df -B1 --output=avail /d | tail -1)" >> "$log"
python "$(dirname "$0")/e2_fetch.py" "$leg" "$(cygpath -w "$out")" --workers 8 >> "$log" 2>&1
rc=$?
echo "END $(date '+%F %T') rc=$rc bytes=$(du -sb "$out" | cut -f1) free=$(df -B1 --output=avail /d | tail -1)" >> "$log"
