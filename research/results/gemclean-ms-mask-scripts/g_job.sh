#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# g_job.sh BIN LOG RUN... : GeMClean runs of research/gemclean-ms-mask.md natively on Windows (Git
# Bash), one at a time, each under the main checkout's tools/heavy_lock.py (shared: 8 slots).
set -u
bin=$1; log=$2; shift 2
here=$(dirname "$(readlink -f "$0")")
PY=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
LOCK=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
echo "START $(date -Is) :: $*" >"$log"
for r in "$@"; do
  mem=6; [ "${r:0:2}" = PM ] && mem=18
  t=$(date +%s)
  $PY $LOCK run --slots 8 --mem $mem -- $PY "$here/runs.py" g "$bin" "$r" >>"$log" 2>&1
  echo "RUN $r rc=$? wall=$(($(date +%s) - t))s $(date -Is)" >>"$log"
done
echo "END $(date -Is)" >>"$log"
