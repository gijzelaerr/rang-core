#!/usr/bin/env bash
# gchain.sh SKY... : GeMClean natively on each sky, each under the main checkout's heavy_lock
# (8 slots, 8 GB), logs in $O/logs/ARM-SKY.log. research/rml-gap.md, amendment A1:
# ARM=G (default) runs at -wgridder-accuracy 1e-6; ARM=Gd at GeMClean's default accuracy.
set -u
here=$(cd "$(dirname "$0")" && pwd)
PY=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
O=D:/rang/outputs/rml-gap-20261113
BIN=$O/bin/gemclean-30d9412.exe
ARM=${ARM:-G}
if [ "$ARM" = G ]; then EXTRA="-wgridder-accuracy 1e-6"; else EXTRA=""; fi
for sky in "$@"; do
  log=$O/logs/$(echo "$ARM" | tr 'A-Z' 'a-z')-$sky.log
  echo "START $(date -Is) $ARM $sky $EXTRA" >"$log"
  t=$(date +%s)
  # shellcheck disable=SC2086
  $PY C:/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 8 --mem 8 -- $PY "$here/runs.py" g "$BIN" "$sky" "$ARM" $EXTRA >>"$log" 2>&1
  echo "END $(date -Is) rc=$? wall=$(($(date +%s) - t))s" >>"$log"
done
