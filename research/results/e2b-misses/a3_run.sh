#!/bin/bash
# Arm A3 in WSL (research/e2b-misses.md 9.26), run by the caller under the
# main checkout's heavy_lock.py. W is WSL ext4, P the result directory on D:.
#   a3_run.sh lbase        luno4.ms's FIELD_ID 0 rows -> $W/luno0.ms
#   a3_run.sh L            CASA Gpol on a copy (casa-m90's K, G, B)
#   a3_run.sh S            the simulation; sim.ms then copied to $P/S for rang
#   a3_run.sh xbase        e2b.ms's FIELD_ID 0 rows, FLAG after calibrate;
#                          then copied to $P/X/x17.ms for rang
#   a3_run.sh X            CASA Gpol CC, CM, CR on $W/x17.ms
#   a3_run.sh clean NAME   remove $W/NAME
set -u
W=$HOME/e2b-gpol-20261115
P=/mnt/d/rang/outputs/e2b-gpol-20261115
S=/mnt/c/Users/gijsm/Worktrees/rang/e2b-gpol/research/results/e2b-misses
IMG=rang-o-casa:6.7.6.14
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
mkdir -p "$W/scripts" "$W/L" "$W/S" "$W/X" "$W/tabs"
cp "$S"/a3_casa.py "$S"/a2_casa.py "$W/scripts/"
dk() {  # command
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=1 -v "$W:/w:rw" -v "$P:/p:rw" -v /mnt/d/rang:/d:ro -w /tmp "$IMG" sh -c "$1"
}
py() { dk "/opt/casa/bin/python -I /w/scripts/a3_casa.py $*"; }
out() {  # tables of a run -> $P/NAME/casa
  mkdir -p "$P/$1/casa"
  for t in "$W/$1"/Gpol*; do rm -rf "$P/$1/casa/$(basename "$t")"; cp -a "$t" "$P/$1/casa/"; done
  cp "$W/$1/casa.log" "$P/$1/" 2>/dev/null
}
case "$1" in
  lbase)
    rm -rf "$W/luno0.ms"
    py base /d/outputs/chi-offset-20261113-03-luno-s1/base/luno4.ms /w/luno0.ms /p/L/base.json ;;
  L)
    rm -rf "$W/tabs/luno"; mkdir -p "$W/tabs/luno"
    for n in K G B; do cp -a /mnt/d/rang/outputs/chi-offset-20261113-03-luno-s1/casa-m90/tables/$n "$W/tabs/luno/"; done
    py tasks /p/L/spec.json /p/L/result.json; rc=$?
    out L; rm -rf "$W/L/luno.ms"; exit $rc ;;
  S)
    py tasks /p/S/spec.json /p/S/result.json; rc=$?
    out S
    if [ $rc -eq 0 ]; then rm -rf "$P/S/sim.ms"; cp -a "$W/S/sim.ms" "$P/S/sim.ms" || rc=4; fi
    rm -rf "$W/S/simpt.ms"; exit $rc ;;
  xbase)
    rm -rf "$W/x17.ms"
    py base /d/data/e2-b/e2b.ms /w/x17.ms /p/X/base.json || exit $?
    py tasks /p/Xprep/spec.json /p/Xprep/result.json || exit $?
    rm -rf "$P/X/x17.ms"; cp -a "$W/x17.ms" "$P/X/x17.ms" ;;
  X)
    for d in cc cm cr; do rm -rf "$W/tabs/$d"; mkdir -p "$W/tabs/$d"; done
    for n in K G B; do
      cp -a "$R/casa/tables/$n" "$W/tabs/cc/"
      cp -a /mnt/d/rang/outputs/e2b-arms-20261114/a2/match-ones/tables/$n "$W/tabs/cm/"
      cp -a "$R/rang-run/calibrate/$n" "$W/tabs/cr/"
    done
    py tasks /p/X/spec.json /p/X/result.json; rc=$?
    out X; exit $rc ;;
  clean)
    rm -rf "${W:?}/$2" ;;
esac
