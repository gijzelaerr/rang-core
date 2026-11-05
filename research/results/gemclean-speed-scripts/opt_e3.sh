#!/usr/bin/env bash
# E3: resyncs take 19-43 % of GeMClean coarse at -j 1, nearly all triggered by the tau certificate.
# Does a lower -tau-min pay, and what does it cost? Same binary, all skies, -j 1 and -j 16, one repeat.
set -u
ROOT=/home/gijsm/Github/rang
O=/mnt/d/rang/outputs/20261104-speed
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
W=/home/gijsm/Build/tmp/20261104-opt3
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
LOCK=/home/gijsm/.rang-heavy.lock
py=$ROOT/.venv/bin/python
SKIES="s1 s2 s3 h1 h2 h3 h4"
say() { { echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "$1"; } > "$STATUS"; echo "$1"; }
mkdir -p "$W/data" "$O/opt/e3"
cp "$O/gemclean-3945394" "$W/gemclean"
for s in s1 s2 s3; do cp -r $B/data/$s.ms $B/data/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r $H/data/$s.ms $H/data/$s.json "$W/data/"; done
export BENCH_DATA=$W/data BENCH_LOCK=$LOCK
cd /mnt/c/Users/gijsm/Github/rang || exit 3
for t in 0.3 0.2 0.1; do
  for ds in $SKIES; do
    say "E3 -tau-min $t, $ds"
    GEMCLEAN_ARGS="-single -wgridder-accuracy 1e-4 -tau-min $t" BENCH_THREADS="16 1" BENCH_MODES=abs \
      bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$W/out/tau$t" "$ds" | cut -c1-100
  done
  rm -rf "$W/out/tau$t/ms"
  cp -r "$W/out/tau$t" "$O/opt/e3/"
done
rm -rf "$W"
cd "$ROOT" || exit 3
for t in 0.3 0.2 0.1; do
  for ds in $SKIES; do
    case $ds in s*) P=$B/prep/$ds; C=$B/data/$ds.json ;; *) P=$O/prep-h/$ds; C=$H/data/$ds.json ;; esac
    say "Scoring E3 tau $t $ds"
    flock $LOCK $py examples/gemclean_bench_compare.py score "$P" "$C" "$O/opt/e3/tau$t" "$O/opt/e3/tau$t/score-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs "$ds-abs-nominres-fast-j16" | cut -c1-120
  done
done
say "E3 finished; nothing running."
