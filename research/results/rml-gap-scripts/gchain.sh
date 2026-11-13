#!/usr/bin/env bash
# gchain.sh SKY... : GeMClean (arm G) on each sky natively, each under the main checkout's
# heavy_lock (8 slots, 8 GB), logs in $O/logs/g-SKY.log. research/rml-gap.md.
set -u
here=$(cd "$(dirname "$0")" && pwd)
PY=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
O=D:/rang/outputs/rml-gap-20261113
BIN=$O/bin/gemclean-30d9412.exe
for sky in "$@"; do
  log=$O/logs/g-$sky.log
  echo "START $(date -Is) $sky" >"$log"
  t=$(date +%s)
  $PY C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 8 --mem 8 -- $PY "$here/runs.py" g "$BIN" "$sky" >>"$log" 2>&1
  echo "END $(date -Is) rc=$? wall=$(($(date +%s) - t))s" >>"$log"
done
