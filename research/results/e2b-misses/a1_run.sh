#!/bin/bash
# Arm A1 in WSL (research/e2b-misses.md 9.2). CPU steps run under the main
# checkout's heavy_lock.py (the caller wraps them).
#   a1_run.sh mini   41 rows of R/casa/e2b.ms and rang's tables -> $W/a1 (disk work)
#   a1_run.sh casa   C2, M1, M2 applycal calls (spec from a1_rang.py spec)
set -u
W=$HOME/e2b-arms-20261114
P=/mnt/d/rang/outputs/e2b-arms-20261114
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
S=/mnt/c/Users/gijsm/Worktrees/rang/e2b-arms/research/results/e2b-misses
IMG=rang-o-casa:6.7.6.14
mkdir -p "$W/scripts" "$W/a1" "$P/a1"; cp "$S"/a1_casa.py "$W/scripts/"
dk() {
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=1 -v "$W:/w:rw" -v "$P:/p:rw" -v "$R:/r:ro" -w /tmp "$IMG" sh -c "$1"
}
case "$1" in
  mini)
    rm -rf "$W/a1/tables" "$W/a1/mini.ms"; cp -a "$R/rang-run/calibrate" "$W/a1/tables"
    dk "/opt/casa/bin/python -I /w/scripts/a1_casa.py mini /r/casa/e2b.ms /r/casa/e2b.ms.flagversions/flags.rang_apply_20261112T013707Z /r/g2b-applycal-cells.json /w/a1/mini.ms /p/a1/mini.json"
    rc=$?; rm -rf "$P/a1/mini.ms"; cp -a "$W/a1/mini.ms" "$P/a1/mini.ms"; exit $rc ;;
  casa)
    dk "/opt/casa/bin/python -I /w/scripts/a1_casa.py run /w/a1/mini.ms /p/a1/a1-spec.json /w/a1/work /w/a1/casa"
    rc=$?; rm -rf "$P/a1/casa"; cp -a "$W/a1/casa" "$P/a1/casa"; cp "$W/a1/work/casa.log" "$P/a1/" 2>/dev/null; exit $rc ;;
esac
