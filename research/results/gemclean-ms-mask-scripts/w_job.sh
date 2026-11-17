#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# w_job.sh LOG RUN... : WSClean runs of research/gemclean-ms-mask.md from WSL, one at a time, each
# under the main checkout's tools/heavy_lock.py (shared: 8 slots; memory per run below).
set -u
log=$1; shift
here=$(dirname "$(readlink -f "$0")")
LOCK=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
echo "START $(date -Is) pid $$ :: $*" >"$log"
for r in "$@"; do
  mem=8; [ "${r:0:2}" = PM ] && mem=16
  t=$(date +%s)
  nice -n 10 python3 $LOCK run --slots 8 --mem $mem -- python3 "$here/runs.py" w "$r" >>"$log" 2>&1
  echo "RUN $r rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$log"
done
echo "END $(date -Is)" >>"$log"
