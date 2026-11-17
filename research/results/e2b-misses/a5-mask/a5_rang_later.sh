#!/bin/bash
# GeMClean fields 1, 2 of A5, enqueued only once 46 GB fit (so they do not head-block the FIFO).
export MSYS_NO_PATHCONV=1
L=C:/Users/gijsm/Github/rang/tools/heavy_lock.py
for r in 1:J1939m6342 2:J1833m2103; do IFS=: read -r fid tag <<< "$r"
  until python $L status | head -2 | grep -qE "shared: [0-9]+/16 slots, [0-2]/48 GB"; do sleep 60; done
  python $L run --slots 4 --mem 46 -- "C:/Program Files/Git/bin/bash.exe" \
    C:/Users/gijsm/Worktrees/rang/gemclean-iquv-mask/research/results/e2b-misses/a5-mask/a5_rang.sh e2b "$fid" "$tag"
done
