#!/bin/bash
# 9.18's queue.
#   a5_queue.sh wsl       (WSL) ext4 copy, C10 run, 3 nosi runs at 1e-6, drop the copy
#   a5_queue.sh windows   (Git Bash) unit on, 3 GeMClean runs at 1e-6, unit off
set -u
S=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  wsl)
    L=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
    [ -d "$HOME/e2b-close/a5.ms" ] || python3 $L run --slots 2 --mem 4 -- bash "$S/a5_run.sh" copy || exit 1
    python3 $L run --slots 1 --mem 2 -- bash "$S/a5_run.sh" fixcat || exit 1
    python3 $L run --slots 2 --mem 10 -- bash "$S/a5_run.sh" wsclean default 2 J1833m2103 0.0001
    for r in 2:J1833m2103 1:J1939m6342 0:J1331p3030; do
      IFS=: read -r fid tag <<< "$r"
      python3 $L run --slots 2 --mem 10 -- bash "$S/a5_run.sh" wsclean nosi "$fid" "$tag" 1e-06
    done
    touch /mnt/d/rang/outputs/e2b-close-20261115/a5/wsclean.done ;;
  windows)
    L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
    PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
    GB=$(cygpath -m "$(command -v bash)")
    # the ext4 copy reads RANG_FLAG, which "unit on" renames: wait for it
    until [ -f D:/rang/outputs/e2b-close-20261115/a5/a5-copy.json ]; do sleep 30; done
    # gemclean-iquv-mask reads the same MS for its private copy: no rename before it is done
    until [ -f D:/rang/outputs/gemclean-iquv-mask-20261115/slim.json ]; do sleep 30; done
    MSYS_NO_PATHCONV=1 wsl -e python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run \
      --slots 1 --mem 2 -- bash "/mnt/c/Users/gijsm/Worktrees/rang/e2b-close/research/results/e2b-misses/a4_run.sh" unit on || exit 1
    for r in 2:J1833m2103 1:J1939m6342 0:J1331p3030; do
      IFS=: read -r fid tag <<< "$r"
      "$PY" $L run --slots 4 --mem 46 -- "$GB" "$S/a5_rang.sh" "$fid" "$tag" 1e-06
    done
    MSYS_NO_PATHCONV=1 wsl -e python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run \
      --slots 1 --mem 2 -- bash "/mnt/c/Users/gijsm/Worktrees/rang/e2b-close/research/results/e2b-misses/a4_run.sh" unit off
    touch D:/rang/outputs/e2b-close-20261115/a5/rang.done ;;
esac
