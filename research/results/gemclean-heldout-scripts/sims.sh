#!/usr/bin/env bash
set -uo pipefail
W=/home/gijsm/Worktrees/rang/gemclean-heldout
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim
mkdir -p $S/data $S/prep $S/scores
cd $W
py=$W/.venv/bin/python
tsv=$S/timing.tsv
[ -f $tsv ] || printf 'step\twall_s\tmax_rss_kb\n' > $tsv
timed(){ step=$1; shift; /usr/bin/time -f "%e %M" -o $S/.t "$@"; rc=$?; printf '%s\t%s\t%s\n' "$step" "$(cut -d' ' -f1 $S/.t)" "$(cut -d' ' -f2 $S/.t)" >> $tsv; return $rc; }
LOCK=/home/gijsm/.rang-heavy.lock
for h in 1 2 3 4; do
  ds=h$h
  sz="--size 2048 --scale 1.5"; [ $h = 3 ] && sz="--size 4096 --scale 1.5"
  if [ ! -d $S/data/$ds.ms ]; then
    timed "simulate $ds" flock $LOCK $py $W/examples/gemclean_bench_simulate.py $S/data/$ds.ms --sky H$h $sz --catalogue $S/data/$ds.json --noise-out $S/data/$ds.noise.c64 || exit 1
  fi
done
export BENCH_DATA=$S/data
link(){ # hardlink tree, so that a run directory does not copy the MS (C: is nearly full)
  run=$1; shift
  mkdir -p $run/ms
  for ds in "$@"; do
    [ -d $run/ms/$ds.ms ] && continue
    cp -al $S/data/$ds.ms $run/ms/$ds.ms
    (cd $run/ms/$ds.ms && find . -maxdepth 1 -type f ! -name table.lock -printf '%f
' | sort | xargs sha256sum) > $run/ms/$ds.ms-sha256-before.txt
  done
}
link $S/wsclean-dirty h1 h2 h3 h4
BENCH_MODES=dirty BENCH_GRIDS="nominres" BENCH_LOOPS=fast BENCH_THREADS=16 bash $W/examples/gemclean_bench_run.sh wsclean $S/wsclean-dirty h1 h2 h3 h4
for h in 1 2 3 4; do
  ds=h$h
  sz="--size 2048 --scale 1.5"; [ $h = 3 ] && sz="--size 4096 --scale 1.5"
  [ -d $S/prep/$ds ] || timed "prepare $ds" flock $LOCK $py $W/examples/gemclean_bench_compare.py prepare $S/data/$ds.ms $S/data/$ds.json $S/prep/$ds $sz --noise $S/data/$ds.noise.c64 --wsclean-dirty $S/wsclean-dirty/$ds-dirty-nominres-fast-j16 > $S/prep/$ds.log 2>&1
done
echo PREPARED
