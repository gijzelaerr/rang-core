#!/usr/bin/env bash
# imaging matrix after sims.sh
set -uo pipefail
W=/home/gijsm/Worktrees/rang/gemclean-heldout
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim
cd $W
export BENCH_DATA=$S/data
link(){ run=$1; shift; mkdir -p $run/ms
  for ds in "$@"; do
    [ -d $run/ms/$ds.ms ] && continue
    cp -al $S/data/$ds.ms $run/ms/$ds.ms
    (cd $run/ms/$ds.ms && find . -maxdepth 1 -type f ! -name table.lock -printf '%f
' | sort | xargs sha256sum) > $run/ms/$ds.ms-sha256-before.txt
  done
}
link $S/wsclean h1 h2 h3 h4
link $S/gemclean h1 h2 h3 h4
export BENCH_THREADS=16 BENCH_MODES=abs
BENCH_GRIDS=nominres BENCH_LOOPS="fast hogbom" bash $W/examples/gemclean_bench_run.sh wsclean $S/wsclean h1 h2 h3 h4
bash $W/examples/gemclean_bench_gemclean.sh $S/gemclean-f0ca931 $S/gemclean h1 h2 h3 h4
echo MATRIX-DONE
