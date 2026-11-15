#!/bin/bash
# Arm A5 (research/e2b-misses.md 9.18 and its amendment), from Git Bash on
# Windows. WSL steps book the lock once, from the WSL side, at what they use;
# GeMClean steps book it from Windows. The file copy to ext4 runs outside it.
#   a5_queue.sh e2b    private copy (slim), its ext4 copy, then three lanes:
#                      GeMClean masked, WSClean masked, WSClean unmasked
#   a5_queue.sh rest   after the first pass (2026-11-15): FLAG_CATEGORY on the ext4
#                      copy, GeMClean fields 1 and 2 (booked 46 GB: field 0 held
#                      40 GB private, the coordinator), WSClean both lanes, all fields
set -u
export MSYS_NO_PATHCONV=1
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
LW=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
GB="C:/Program Files/Git/bin/bash.exe"
W=/mnt/c/Users/gijsm/Worktrees/rang/gemclean-iquv-mask/research/results/e2b-misses
S=C:/Users/gijsm/Worktrees/rang/gemclean-iquv-mask/research/results/e2b-misses
P=D:/rang/outputs/gemclean-iquv-mask-20261115
RS=${RANG_SLOTS:-4}
wsl_job() { wsl.exe -e python3 "$LW" run --slots "$1" --mem "$2" -- bash "$W/a5_run.sh" "${@:3}"; }
rang_job() { python "$L" run --slots "$RS" --mem "$1" -- "$GB" "$S/a5_rang.sh" "${@:2}"; }
FIELDS="0:J1331p3030 1:J1939m6342 2:J1833m2103"
case "$1" in
  e2b)
    [ -f "$P/slim.json" ] || wsl_job 1 4 slim || exit 1
    wsl.exe -e bash "$W/a5_run.sh" ext4 || exit 1
    lane_rang() { for r in $FIELDS; do IFS=: read -r fid tag <<< "$r"
        rang_job 46 e2b "$fid" "$tag"; done; }
    lane_ws() { for r in $FIELDS; do IFS=: read -r fid tag <<< "$r"
        wsl_job 2 12 wsclean "$fid" "$tag" "$1"; done; }
    lane_rang > "$P/lane-rang.log" 2>&1 & a=$!
    lane_ws mask > "$P/lane-wsclean-mask.log" 2>&1 & b=$!
    lane_ws nomask > "$P/lane-wsclean-nomask.log" 2>&1 & c=$!
    wait $a $b $c
    echo "e2b done" ;;
  rest)
    wsl_job 1 2 flagcat || exit 1
    lane_rang() { for r in 1:J1939m6342 2:J1833m2103; do IFS=: read -r fid tag <<< "$r"
        rang_job 46 e2b "$fid" "$tag"; done; }
    lane_ws() { for r in $FIELDS; do IFS=: read -r fid tag <<< "$r"
        wsl_job 2 12 wsclean "$fid" "$tag" "$1"; done; }
    lane_rang > "$P/lane-rang2.log" 2>&1 & a=$!
    lane_ws mask > "$P/lane-wsclean-mask2.log" 2>&1 & b=$!
    lane_ws nomask > "$P/lane-wsclean-nomask2.log" 2>&1 & c=$!
    wait $a $b $c
    echo "rest done" ;;
esac
