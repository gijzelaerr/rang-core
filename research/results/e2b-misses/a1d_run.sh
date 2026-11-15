#!/bin/bash
# Arm A1d container side in WSL (research/e2b-misses.md 9.13); the caller
# wraps it in the main checkout's heavy_lock.py (1 slot).
set -u
W=$HOME/e2b-pastro-20261114
P=/mnt/d/rang/outputs/e2b-pastro-20261114
S=/mnt/c/Users/gijsm/Worktrees/rang/e2b-pastro/research/results/e2b-misses
mkdir -p "$W/a1d" "$P/a1d"
rm -rf "$W/a1d/mini.ms"; cp -a /mnt/d/rang/outputs/e2b-arms-20261114/a1/mini.ms "$W/a1d/mini.ms"
cp "$S/a1d_casa.py" "$W/"
s=$(date +%s)
docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
  -e OMP_NUM_THREADS=1 -v "$W:/w:rw" -w /tmp rang-o-casa:6.7.6.14 \
  /opt/casa/bin/python -I /w/a1d_casa.py /w/a1d/mini.ms /w/a1d/out
rc=$?
echo "rc=$rc secs=$(( $(date +%s) - s ))"
cp -a "$W/a1d/out/." "$P/a1d/"
rm -rf "$W/a1d/mini.ms"
exit $rc
