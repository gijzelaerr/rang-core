#!/usr/bin/env bash
# real2.sh THRESHOLD_JY JOB...   jobs: fast plain gem autoest
set -uo pipefail
thr=$1; shift
W=/home/gijsm/Worktrees/rang/gemclean-heldout
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
BIN=/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim/gemclean-f0ca931
IMG=rang-o-casa:6.7.6.14
SIZE=${REAL_SIZE:-4096}; SCALE=${REAL_SCALE:-3}
mkdir -p $S/run/tmp $S/run/timing
LOCK=/home/gijsm/.rang-heavy.lock
ws(){ name=$1; shift
  [ -f $S/run/timing/$name.txt ] && return 0
  flock $LOCK bash -c '
    cat /proc/loadavg > '$S'/run/timing/'$name'.load
    /usr/bin/time -v -o '$S'/run/timing/'$name'.txt docker run --rm --user $(id -u):$(id -g) --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 -v '$S':/data:ro -v '$S'/run:/run -w /run '$IMG' \
    wsclean -gridder wgridder -data-column DATA -field 0 -size '$SIZE' '$SIZE' -scale '$SCALE'asec -weight briggs 0.5 -pol I -j 16 -abs-mem 20 -no-update-model-required -temp-dir /run/tmp -no-min-grid-resolution -wgridder-accuracy 1e-6 -niter 1000000 -nmiter 0 -gain 0.1 -mgain 0.8 "$@" -name /run/'$name' /data/${MS:-cal2}.ms > '$S'/run/'$name'.log 2>&1
    echo "'$name' rc=$?"
    cat /proc/loadavg >> '$S'/run/timing/'$name'.load
  ' _ "$@"
}
gem(){ name=$1; shift
  [ -f $S/run/timing/$name.txt ] && return 0
  flock $LOCK bash -c '
    cat /proc/loadavg > '$S'/run/timing/'$name'.load
    OMP_NUM_THREADS=16 RAYON_NUM_THREADS=16 /usr/bin/time -v -o '$S'/run/timing/'$name'.txt '$BIN' -name '$S'/run/'$name' -size '$SIZE' '$SIZE' -scale '$SCALE'asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 "$@" -data-column DATA -field 0 -j 16 '$S'/${MS:-cal2}.ms > '$S'/run/'$name'.log 2>&1 &
    p=$!
    ( while kill -0 $p 2>/dev/null; do
        rss=$(ps -o rss= --ppid $p 2>/dev/null | sort -n | tail -1); rss=${rss:-0}
        echo $rss >> '$S'/run/timing/'$name'.rss
        if [ "$rss" -gt 24500000 ]; then echo "'$name' RSS over 24.5 GB, killing"; pkill -P $p; fi
        sleep 10
      done ) &
    wait $p; echo "'$name' rc=$?"
    cat /proc/loadavg >> '$S'/run/timing/'$name'.load
  ' _ "$@"
}
tag=${thr/0./}
for j in "$@"; do
  case $j in
    dirty) ws ${MS:-cal2}-dirty -niter 0 -make-psf ;;
    fast) ws ${MS:-cal2}-$tag-fast -abs-threshold $thr ;;
    plain) ws ${MS:-cal2}-$tag-plain -abs-threshold $thr -no-fast-subminor ;;
    gem) gem ${MS:-cal2}-$tag-gem -abs-threshold $thr ;;
  esac
done
:
echo REAL2-DONE "$@"
