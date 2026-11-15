#!/bin/bash
# 9.22's queue (Git Bash). Stops at the first failed step; R/casa/e2b.ms is only read.
set -u
S=$(cd "$(dirname "$0")" && pwd)
P=D:/rang/outputs/e2b-2b-20261115
W=/mnt/c/Users/gijsm/Worktrees/rang/e2b-2b/research/results/e2b-misses
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
mkdir -p "$P"
free() { powershell -c "(Get-PSDrive D).Free/1GB" | tr -d '\r'; }
wl() {  # slots mem args...
  local n=$1 m=$2; shift 2
  MSYS_NO_PATHCONV=1 wsl -e python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run \
    --slots "$n" --mem "$m" -- bash "$W/c2b_run.sh" "$@"
}
win() {  # slots mem args...
  local n=$1 m=$2; shift 2
  local s=$(date +%s)
  "$PY" $L run --slots "$n" --mem "$m" -- "$PY" "$S/c2b_win.py" "$@" > "$P/win-$1.out" 2>&1
  local rc=$?
  echo "$(date -Is) win $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
  return $rc
}
echo "$(date -Is) free_start $(free)" >> "$P/disk.log"
[ -f "$P/hash_src.json" ] || win 1 4 hash_src "$P/hash_src.json" || exit 1
[ -f "$P/make.json" ] || wl 2 8 make || exit 1
"$PY" - "$P/hash_src.json" "$P/make.json" <<'EOF' || { echo "C11 not met" >> "$P/runs.log"; exit 2; }
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
ok = a["rows"] == b["rows"] and a["data_sha256"] == b["data_sha256"] and a["flag_sha256"] == b["flag_sha256"]
print("C11", ok); sys.exit(0 if ok else 1)
EOF
echo "$(date -Is) C11 met" >> "$P/runs.log"
echo "$(date -Is) free_after_make $(free)" >> "$P/disk.log"
wl 2 12 casa || exit 3
wl 2 8 casa_done || exit 4
f=$(free); echo "$(date -Is) free_before_copyout $f" >> "$P/disk.log"
python3 -c "import sys; sys.exit(0 if float('$f') > 150 + 90 + 40 else 1)" 2>/dev/null \
  || "$PY" -c "import sys; sys.exit(0 if float('$f') > 150 + 90 + 40 else 1)" || { echo "D: too full for copyout" >> "$P/runs.log"; exit 5; }
wl 2 8 copyout || exit 6
wl 1 2 drop
echo "$(date -Is) free_after_copyout $(free)" >> "$P/disk.log"
win 4 16 apply "$P/apply.json" || exit 7
win 1 4 compare c9 "$P/c9.json" || exit 8
win 1 4 compare measure "$P/g2b-new.json" || exit 9
win 1 4 compare beside "$P/p-change.json"
echo "$(date -Is) free_end $(free)" >> "$P/disk.log"
touch "$P/done"
