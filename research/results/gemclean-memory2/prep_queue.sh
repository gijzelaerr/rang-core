#!/bin/bash
# research/gemclean-memory2.md: rebuild E2-B's three calibrator-field inputs as
# e2b-misses 9.28 did (c3/c3_queue.sh prep and field, without CASA, the 2b
# compare and the WSL copy back): rang's packed flags, E on ext4 (C11 against
# c2b/hash_src.json), per field the subset with WEIGHT = 1, the D: copy (hashed
# on both sides) and rang's apply into E2C_RANG_CORRECTED_DATA. Git Bash.
#   prep_queue.sh            all three fields, then E dropped
set -u
export MSYS_NO_PATHCONV=1
S=$(cd "$(dirname "$0")" && pwd -W)
C3=$(cd "$S/../e2b-misses/c3" && pwd -W)
P=D:/rang/outputs/gemclean-memory2-20261116
WT=$(cd "$S/../../.." && pwd -W)
WS=/mnt/c/Users/gijsm/Worktrees/rang/gemclean-memory2/research/results/gemclean-memory2
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
LW=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
PY=$WT/.venv/Scripts/python.exe
GB="C:/Program Files/Git/bin/bash.exe"
FLOOR=150   # GiB kept free on D:
mkdir -p "$P"
free() { powershell -c "[math]::Floor((Get-PSDrive D).Free/1GB)" | tr -d '\r'; }
need() {
  local f; f=$(free); echo "$(date -Is) free $f need $1 ($2)" >> "$P/disk.log"
  [ $((f - $1)) -ge $FLOOR ] || { echo "$(date -Is) D: too full for $2 ($f free)" >> "$P/runs.log"; exit 9; }
}
wl() { local n=$1 m=$2; shift 2; wsl.exe -e python3 "$LW" run --slots "$n" --mem "$m" -- bash "$WS/prep_run.sh" "$@"; }
win() {
  local n=$1 m=$2 lab=$3; shift 3; local s; s=$(date +%s)
  "$PY" $L run --slots "$n" --mem "$m" -- "$@" > "$P/win-$lab.out" 2>&1; local rc=$?
  echo "$(date -Is) win $lab rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"; return $rc
}
ok() { grep -qE "^[^ ]+ $1 rc=0 " "$P/runs.log" 2>/dev/null; }
dsha() {
  local s; s=$(date +%s)
  "$PY" $L run --slots 1 --mem 2 -- "$GB" -c "cd '$P/f$1.ms' && find . -type f -print0 | sort -z | xargs -0 sha256sum | sed 's/ [*][.]/  ./'" > "$P/$2"
  local rc=$?; echo "$(date -Is) dsha $1 $2 rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"; return $rc
}
[ -f "$P/rang-flag-after-apply.npy" ] || win 1 4 npy "$PY" "$C3/c3_flags.py" write "$P/rang-flag-after-apply.npy" || exit 1
ok make || { need 10 make; wl 2 8 make || exit 2; }
"$PY" - "$C3/../c2b/hash_src.json" "$P/make.json" <<'PYEOF' || { echo "C11 not met" >> "$P/runs.log"; exit 3; }
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
ok = a["rows"] == b["rows"] and a["data_sha256"] == b["data_sha256"] and a["flag_sha256"] == b["flag_sha256"]
print("C11", ok); sys.exit(0 if ok else 1)
PYEOF
echo "$(date -Is) C11 met" >> "$P/runs.log"
for f in 2 0 1; do
  [ -f "$P/apply$f.json" ] && continue
  case $f in 0) g=32;; 1) g=33;; 2) g=10;; esac
  need $(( g * 14 / 10 )) "field $f"
  wl 2 8 subset "$f" || exit 11
  wl 1 2 copyout "$f" || exit 12
  dsha "$f" "s$f-d.sha256" && cmp "$P/s$f-ext4.sha256" "$P/s$f-d.sha256" || exit 12
  wl 1 2 drops "$f"
  win 4 16 "apply$f" "$PY" "$S/prep_win.py" apply "$f" "$P/apply$f.json" || exit 13
  dsha "$f" "f$f-d.sha256" || exit 14
  echo "$(date -Is) field $f ready, free $(free)" >> "$P/runs.log"
done
wl 1 2 drope
echo "$(date -Is) prep done, free $(free)" >> "$P/runs.log"
touch "$P/prep.done"
