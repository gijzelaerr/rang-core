#!/usr/bin/env bash
# E5: band limit from the geometry. All skies, -j 1 and -j 16, at -tau-min 0.5 and 0.2, coarse gridding; scored at -j 16.
set -u
export PATH=$HOME/.cargo/bin:$PATH
ROOT=/home/gijsm/Github/rang
O=/mnt/d/rang/outputs/20261104-speed
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
W=/home/gijsm/Build/tmp/20261104-opt4
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
LOCK=/home/gijsm/.rang-heavy.lock
py=$ROOT/.venv/bin/python
SKIES="s1 s2 s3 h1 h2 h3 h4"
say() { { echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "$1"; } > "$STATUS"; echo "$1"; }
rsync -a --delete --exclude target --exclude .venv --exclude outputs --exclude .git /mnt/c/Users/gijsm/Worktrees/rang/gemclean-opt3/ "$W/src/"
cd "$W/src/core" || exit 3
flock $LOCK cargo +1.93 test --offline --release --lib gemclean 2>&1 | tail -2 | cut -c1-140
flock $LOCK cargo +1.93 clippy --offline --all-targets 2>&1 | tail -3 | cut -c1-200
flock $LOCK cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -1
mkdir -p "$W/data" "$O/opt/e5"
cp target/gemclean/gemclean "$O/opt/e5/gemclean-band" && cp target/gemclean/gemclean "$W/gemclean"
for s in s1 s2 s3; do cp -r $B/data/$s.ms $B/data/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r $H/data/$s.ms $H/data/$s.json "$W/data/"; done
export BENCH_DATA=$W/data BENCH_LOCK=$LOCK
cd /mnt/c/Users/gijsm/Github/rang || exit 3
for v in "band -tau-min 0.5" "bandtau -tau-min 0.2"; do
  set -- $v; label=$1; shift
  for ds in $SKIES; do
    say "E5 $label, $ds"
    GEMCLEAN_ARGS="-single -wgridder-accuracy 1e-4 -beam-band $*" BENCH_THREADS="16 1" BENCH_MODES=abs \
      bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$W/out/$label" "$ds" | cut -c1-100
  done
  rm -rf "$W/out/$label/ms"
  cp -r "$W/out/$label" "$O/opt/e5/"
done
cd "$ROOT" || exit 3
for label in band bandtau; do
  for ds in $SKIES; do
    case $ds in s*) P=$B/prep/$ds; C=$B/data/$ds.json ;; *) P=$O/prep-h/$ds; C=$H/data/$ds.json ;; esac
    say "Scoring E5 $label $ds"
    flock $LOCK $py examples/gemclean_bench_compare.py score "$P" "$C" "$O/opt/e5/$label" "$O/opt/e5/$label/score-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs "$ds-abs-nominres-fast-j16" | cut -c1-120
  done
done
rm -rf "$W"
say "E5 finished; nothing running."
