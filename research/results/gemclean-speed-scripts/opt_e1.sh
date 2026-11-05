#!/usr/bin/env bash
# 1. Score the native pass on the held-out skies (prep arrays rebuilt, the old ones were removed).
# 2. E1: GeMClean -single at coarser gridder accuracy, all skies, same binary as the native pass.
set -u
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
ROOT=/home/gijsm/Github/rang
O=/mnt/d/rang/outputs/20261104-speed
N=$O/native
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
W=/home/gijsm/Build/tmp/20261104-opt
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
LOCK=/home/gijsm/.rang-heavy.lock
py=$ROOT/.venv/bin/python
say() { { echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "$1"; } > "$STATUS"; echo "$1"; }
cd "$ROOT" || exit 3
for ds in h1 h2 h3 h4; do
  sz="--size 2048 --scale 1.5"; [ $ds = h3 ] && sz="--size 4096 --scale 1.5"
  P=$O/prep-h/$ds
  say "Preparing and scoring $ds of the native pass"
  mkdir -p "$O/prep-h"
  [ -f "$P/uvw.f64" ] || flock $LOCK $py examples/gemclean_bench_compare.py prepare "$H/data/$ds.ms" "$H/data/$ds.json" "$P" $sz \
    --noise "$H/data/$ds.noise.c64" --wsclean-dirty "$H/wsclean-dirty/$ds-dirty-nominres-fast-j16" > /dev/null
  for im in wsclean gemclean; do
    jobs=$(cd "$N/rep1/$im" && ls | grep "^$ds-.*j16-model.fits" | sed 's/-model.fits//')
    flock $LOCK $py examples/gemclean_bench_compare.py score "$P" "$H/data/$ds.json" "$N/rep1/$im" "$N/scores/$im-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs $jobs | cut -c1-120
  done
done

mkdir -p "$W/data"
cp "$O/gemclean-3945394" "$W/gemclean"
for s in s1 s2 s3; do cp -r $B/data/$s.ms $B/data/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r $H/data/$s.ms $H/data/$s.json "$W/data/"; done
export BENCH_DATA=$W/data BENCH_LOCK=$LOCK
cd /mnt/c/Users/gijsm/Github/rang || exit 3
run_variant() {  # run_variant LABEL REPEATS ARGS
  label=$1; reps=$2; args=$3
  for rep in $(seq 1 "$reps"); do
    for ds in s1 s2 s3 h1 h2 h3 h4; do
      say "E1 $label: repeat $rep of $reps, $ds"
      GEMCLEAN_ARGS="$args" BENCH_THREADS="16 1" BENCH_MODES=abs bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$W/out/$label/rep$rep" "$ds" | cut -c1-100
    done
    rm -rf "$W/out/$label/rep$rep/ms"
  done
  mkdir -p "$O/opt/e1"
  cp -r "$W/out/$label" "$O/opt/e1/" && rm -rf "$W/out/$label"
}
run_variant single-1e4 3 "-single -wgridder-accuracy 1e-4"
run_variant single-1e5 1 "-single -wgridder-accuracy 1e-5"
cd "$ROOT" || exit 3
for label in single-1e4 single-1e5; do
  for ds in s1 s2 s3 h1 h2 h3 h4; do
    case $ds in s*) P=$B/prep/$ds; C=$B/data/$ds.json ;; *) P=$O/prep-h/$ds; C=$H/data/$ds.json ;; esac
    say "Scoring E1 $label $ds"
    jobs=$(cd "$O/opt/e1/$label/rep1" && ls | grep "^$ds-.*j16-model.fits" | sed 's/-model.fits//')
    flock $LOCK $py examples/gemclean_bench_compare.py score "$P" "$C" "$O/opt/e1/$label/rep1" "$O/opt/e1/$label/score-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs $jobs | cut -c1-120
  done
done
rm -rf "$W"
say "E1 finished; nothing running."
