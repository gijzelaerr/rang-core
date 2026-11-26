#!/bin/bash
# SPDX-License-Identifier: MIT
# research/k-ambiguity.md section 9 on nash: ka_scan.py over every DL4s block's per-scan MSs
# (dl2-data, read only) and E2-N's MS (read only), three at a time, under the heavy lock with
# nice 19 / ionice -c3; outputs in the run root.
set -uo pipefail
R=$HOME/rang-data/outputs/k-ambiguity2-20261126
W=$HOME/Worktrees/rang/k-ambiguity-2
PY=$W/.venv/bin/python
S=$R/ka_scan.py
DL2=$HOME/rang-data/outputs/dl2-data-20261119/ms
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run --slots 1 --mem 6 -- nice -n 19 ionice -c3"
jobs_list() {
  echo "e2n $HOME/rang-data/outputs/e2n-20261116/e2n.ms"
  for b in "$DL2"/*/; do
    b=$(basename "$b")
    for m in "$DL2/$b"/scan*.ms; do echo "$b $m"; done
  done
}
one() {
  local tag=$1 ms=$2 n
  n=$(basename "$ms" .ms)
  mkdir -p "$R/out/$tag"
  [ -s "$R/out/$tag/$n.json" ] && return 0
  $LOCK "$PY" "$S" "$ms" "$R/out/$tag/$n.json" > "$R/out/$tag/$n.out" 2>&1 || echo "FAIL $tag $n" >> "$R/logs/fail.txt"
}
export -f one; export R PY S LOCK
t0=$(date +%s)
jobs_list | xargs -P 3 -L 1 bash -c 'one "$0" "$1"'
echo "wall $(( $(date +%s) - t0 )) s" > "$R/logs/scan_all.time"
