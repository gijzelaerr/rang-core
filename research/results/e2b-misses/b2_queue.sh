#!/bin/bash
# 9.19's queue (Git Bash): waits for 9.18's GeMClean queue (which holds the MS
# in the matched state), then save, CASA, C9, rang, the measure, restore.
set -u
S=$(cd "$(dirname "$0")" && pwd)
P=D:/rang/outputs/e2b-close-20261115/b2
W=/mnt/c/Users/gijsm/Worktrees/rang/e2b-close/research/results/e2b-misses
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
GB=$(cygpath -m "$(command -v bash)")
mkdir -p "$P"
until [ -f D:/rang/outputs/e2b-close-20261115/a5/rang.done ]; do sleep 60; done
wl() {  # slots, b2_run.sh args
  local n=$1; shift
  MSYS_NO_PATHCONV=1 wsl -e python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run \
    --slots "$n" --mem 6 -- bash "$W/b2_run.sh" "$@"
}
free() { powershell -c "(Get-PSDrive D).Free/1GB" | tr -d '\r'; }
echo "free_before $(free)" >> "$P/disk.log"
wl 2 cols save /b/save.json || exit 1
fail=0
wl 2 casa || fail=1
wl 2 cols casa_done /b/casa_done.json || fail=1
wl 2 cols compare CORRECTED_DATA E2C_CASA_FLAG RANG_CORRECTED_DATA RANG_FLAG /b/c9.json || fail=1
if [ $fail = 0 ]; then
  s=$(date +%s)
  "$PY" $L run --slots 4 --mem 16 -- "$PY" "$S/b2_rang.py" "$P/rang.json" > "$P/rang.out" 2>&1 || fail=1
  echo "$(date -Is) rang rc=$fail secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
  echo "free_peak_after_rang $(free)" >> "$P/disk.log"
  wl 2 cols compare CORRECTED_DATA E2C_CASA_FLAG E2C_RANG_CORRECTED_DATA FLAG /b/g2b-new.json || fail=1
  wl 2 cols compare E2C_RANG_CORRECTED_DATA FLAG RANG_CORRECTED_DATA RANG_FLAG /b/p-change.json || fail=1
fi
wl 2 cols restore /b/save.json /b/restore.json
echo "free_after $(free)" >> "$P/disk.log"
touch "$P/done"
exit $fail
