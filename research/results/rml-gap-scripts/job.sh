#!/usr/bin/env bash
# job.sh LOG SLOTS MEM CMD... : CMD under the main checkout's tools/heavy_lock.py as a shared job
# (normal priority), with START, END, the exit code and the wall (lock wait included) in LOG.
# research/rml-gap.md.
set -u
log=$1 slots=$2 mem=$3
shift 3
mkdir -p "$(dirname "$log")"
echo "START $(date -Is) pid $$ :: $*" >"$log"
t=$(date +%s)
python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots "$slots" --mem "$mem" -- "$@" >>"$log" 2>&1
rc=$?
echo "END $(date -Is) rc=$rc wall=$(($(date +%s) - t))s" >>"$log"
exit $rc
