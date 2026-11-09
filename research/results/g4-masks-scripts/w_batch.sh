#!/usr/bin/env bash
# w_batch.sh RUN... : WSClean 3.7 runs of research/g4-masks.md from WSL, one at a time, each under
# tools/heavy_lock.py (which also takes ~/.rang-heavy.lock).
set -u
W=/mnt/c/Users/gijsm/Worktrees/rang/fp-g4-masks
here=$W/research/results/g4-masks-scripts
for r in "$@"; do
  python3 $W/tools/heavy_lock.py run -- python3 $here/runs.py w "$r"
done
