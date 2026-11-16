#!/bin/bash
# e2b-misses 9.28's queue (Git Bash on Windows). Stops at the first failed step.
# e3-20261111-input/e2b.ms and R are only read. One field's copies at a time.
#   c3_queue.sh prep        packed flags npy, E, C11, CASA applycal, casa_done, E's file hashes
#   c3_queue.sh field FID   subset, D: copy, rang's apply, copy back, 2b compare,
#                           then gate 3c's four runs (two lanes), per-field scores, FITS deleted
#   c3_queue.sh finish      pooled scores, drop E
set -u
export MSYS_NO_PATHCONV=1
S=$(cd "$(dirname "$0")" && pwd)
P=D:/rang/outputs/e2b-confirm-20261116
WS=/mnt/c/Users/gijsm/Worktrees/rang/e2b-confirm/research/results/e2b-misses/c3
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
LW=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
PY=C:/Users/gijsm/Worktrees/rang/e2b-confirm/.venv/Scripts/python.exe
GB="C:/Program Files/Git/bin/bash.exe"
FLOOR=180   # GiB: E2-A's e2_diskguard stops its own job at 165
mkdir -p "$P"
free() { powershell -c "[math]::Floor((Get-PSDrive D).Free/1GB)" | tr -d '\r'; }
need() {  # GiB needed: stop unless free - need stays above FLOOR
  local f; f=$(free); echo "$(date -Is) free $f need $1 ($2)" >> "$P/disk.log"
  [ $((f - $1)) -ge $FLOOR ] || { echo "$(date -Is) D: too full for $2 ($f free)" >> "$P/runs.log"; exit 9; }
}
wl() { local n=$1 m=$2; shift 2; wsl.exe -e python3 "$LW" run --slots "$n" --mem "$m" -- bash "$WS/c3_run.sh" "$@"; }
win() {  # slots mem label cmd...
  local n=$1 m=$2 lab=$3; shift 3; local s; s=$(date +%s)
  "$PY" $L run --slots "$n" --mem "$m" -- "$@" > "$P/win-$lab.out" 2>&1; local rc=$?
  echo "$(date -Is) win $lab rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"; return $rc
}
fits46() {  # wait until a 46 GB ticket fits, so it does not head-block the FIFO
  until "$PY" $L status 2>/dev/null | head -2 | grep -qE "shared: [0-9]+/16 slots, [0-2]/48 GB"; do sleep 60; done
}
dsha() {  # native sha256 of every file of the D: copy, in c3_run.sh's format
  local s; s=$(date +%s)
  "$PY" $L run --slots 1 --mem 2 -- "$GB" -c "cd '$P/f$1.ms' && find . -type f -print0 | sort -z | xargs -0 sha256sum" > "$P/$2"
  local rc=$?; echo "$(date -Is) dsha $1 $2 rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"; return $rc
}
tag() { case $1 in 0) echo J1331p3030;; 1) echo J1939m6342;; 2) echo J1833m2103;; esac; }
name() { case $1 in 0) echo J1331+3030;; 1) echo J1939-6342;; 2) echo J1833-2103;; esac; }
case "$1" in
  prep)
    [ -f "$P/rang-flag-after-apply.npy" ] || win 1 4 npy "$PY" "$S/c3_flags.py" write "$P/rang-flag-after-apply.npy" || exit 1
    [ -f "$P/make.json" ] || wl 2 8 make || exit 2
    "$PY" - "$S/../c2b/hash_src.json" "$P/make.json" <<'EOF' || { echo "C11 not met" >> "$P/runs.log"; exit 3; }
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
ok = a["rows"] == b["rows"] and a["data_sha256"] == b["data_sha256"] and a["flag_sha256"] == b["flag_sha256"]
print("C11", ok); sys.exit(0 if ok else 1)
EOF
    echo "$(date -Is) C11 met" >> "$P/runs.log"
    wl 2 12 casa || exit 4
    wl 2 8 casa_done || exit 5
    wl 1 2 filehash || exit 6
    touch "$P/prep.done" ;;
  field)
    f=$2; t=$(tag "$f"); n=$(name "$f")
    case $f in 0) g=32;; 1) g=33;; 2) g=10;; esac   # GiB of the D: copy after rang's apply (DATA and rang's column, 131 kB per row each)
    need $(( g * 14 / 10 + 12 )) "field $f"
    wl 2 8 subset "$f" || exit 11
    wl 1 2 copyout "$f" || exit 12
    dsha "$f" "s$f-d.sha256" && cmp "$P/s$f-ext4.sha256" "$P/s$f-d.sha256" || exit 12
    wl 1 2 drops "$f"
    win 4 16 "apply$f" "$PY" "$S/c3_win.py" apply "$f" "$P/apply$f.json" || exit 13
    dsha "$f" "f$f-d.sha256" || exit 14
    wl 1 2 copyback "$f" || exit 14
    cmp "$P/f$f-d.sha256" "$P/f$f-ext4.sha256" || exit 14
    wl 1 4 compare "$f" || exit 15
    lane_ws() {
      wl 2 4 wsclean dirty "$f" "$t"
      wl 2 4 wsclean clean "$f" "$t"
    }
    lane_rang() {
      fits46; "$PY" $L run --slots 4 --mem 46 -- "$GB" "$S/c3_rang.sh" dirty "$f" "$t"
      if [ "$f" = 2 ]; then m=16; else m=46; fits46; fi   # J1833 cleaned: 9.2 GiB measured (gemclean-memory 5)
      "$PY" $L run --slots 4 --mem $m -- "$GB" "$S/c3_rang.sh" clean "$f" "$t"
    }
    lane_ws > "$P/lane-ws-$f.log" 2>&1 & a=$!
    lane_rang > "$P/lane-rang-$f.log" 2>&1 & b=$!
    wait $a $b
    win 1 6 "score-dirty$f" "$PY" "$S/c3_score.py" dirty-field "$n" || exit 16
    win 1 6 "score-clean$f" "$PY" "$S/c3_score.py" clean-field "$n" || exit 17
    for d in rang-dirty rang-clean wsclean-dirty wsclean-clean; do
      cp "$P/$d/$t/"*mask.json "$P/score/$d-$t-mask.json" 2>/dev/null
      rm -f "$P/$d/$t/"*.fits
    done
    wl 1 2 dropf "$f"
    rm -rf "$P/f$f.ms" "$P/f$f.ms.flagversions"
    echo "$(date -Is) field $f done, free $(free)" >> "$P/runs.log"
    touch "$P/field$f.done" ;;
  finish)
    win 1 2 g2b "$PY" "$S/c3_score.py" g2b "$P/g2b.json"
    win 1 2 dirty "$PY" "$S/c3_score.py" dirty "$P/g3c-dirty.json"
    win 1 2 clean "$PY" "$S/c3_score.py" clean "$P/g3c-clean.json"
    wl 1 2 drope
    echo "$(date -Is) finish free $(free)" >> "$P/runs.log" ;;
esac
