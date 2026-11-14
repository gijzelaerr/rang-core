#!/bin/bash
# Arm A2 in WSL (research/e2b-misses.md 9.1). Run under the main checkout's
# heavy_lock.py by the caller. W is WSL ext4, P the result directory on D:.
#   a2_run.sh base            the FIELD_ID 1, 2 deep copy -> $W/base.ms
#   a2_run.sh case NAME THR   copy base, then the case's tasks (OMP threads THR)
set -u
W=$HOME/e2b-arms-20261114
P=/mnt/d/rang/outputs/e2b-arms-20261114
S=/mnt/c/Users/gijsm/Worktrees/rang/e2b-arms/research/results/e2b-misses
IMG=rang-o-casa:6.7.6.14
mkdir -p "$W/scripts"; cp "$S"/a2_casa.py "$S"/a1_casa.py "$W/scripts/"
dk() {  # threads, command
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS="$1" -v "$W:/w:rw" -v "$P:/p:rw" -w /tmp "$IMG" sh -c "$2"
}
case "$1" in
  base)
    rm -rf "$W/base.ms"
    dk 1 "/opt/casa/bin/python -I /w/scripts/a2_casa.py base /w/src/e2b.ms /w/base.ms /p/a2/base.json" ;;
  case)
    n=$2; rm -rf "$W/$n"; mkdir -p "$W/$n/tables"
    cp -a "$W/base.ms" "$W/$n/e2b.ms"
    dk "$3" "/opt/casa/bin/python -I /w/scripts/a2_casa.py tasks /p/a2/$n/spec.json /p/a2/$n/result.json"
    rc=$?
    rm -rf "$P/a2/$n/tables"; cp -a "$W/$n/tables" "$P/a2/$n/tables"; cp "$W/$n/casa.log" "$P/a2/$n/" 2>/dev/null
    exit $rc ;;
esac
