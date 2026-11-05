#!/usr/bin/env bash
# E2: give WSClean its own tuning knob. minres at -mgain 0.9 and 0.95 (the fast minor loop goes deeper per cycle),
# so that GeMClean's fewer cycles are not just a default against a default. S1 at 0.8 is the control on the host.
set -u
ROOT=/home/gijsm/Github/rang
O=/mnt/d/rang/outputs/20261104-speed
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
W=/home/gijsm/Build/tmp/20261104-opt2
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
LOCK=/home/gijsm/.rang-heavy.lock
py=$ROOT/.venv/bin/python
SKIES="s1 s2 s3 h1 h2 h3 h4"
say() { { echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "$1"; } > "$STATUS"; echo "$1"; }
mkdir -p "$W/data" "$O/opt/e2"
for s in s1 s2 s3; do cp -r $B/data/$s.ms $B/data/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r $H/data/$s.ms $H/data/$s.json "$W/data/"; done
export BENCH_DATA=$W/data BENCH_LOCK=$LOCK BENCH_WSCLEAN_IMAGE=rang-wsclean-native:3.7
cd /mnt/c/Users/gijsm/Github/rang || exit 3
BENCH_THREADS="16 1" BENCH_MODES=abs BENCH_LOOPS=fast BENCH_GRIDS=minres bash examples/gemclean_bench_run.sh wsclean "$W/out/control" s1 | cut -c1-100
for m in 0.9 0.95; do
  for ds in $SKIES; do
    say "E2 WSClean minres -mgain $m, $ds"
    BENCH_WSCLEAN_ARGS="-mgain $m" BENCH_THREADS="16 1" BENCH_MODES=abs BENCH_LOOPS=fast BENCH_GRIDS=minres \
      bash examples/gemclean_bench_run.sh wsclean "$W/out/mgain$m" "$ds" | cut -c1-100
  done
done
rm -rf "$W"/out/*/ms
cp -r "$W"/out/* "$O/opt/e2/"
rm -rf "$W"
cd "$ROOT" || exit 3
for m in mgain0.9 mgain0.95; do
  for ds in $SKIES; do
    case $ds in s*) P=$B/prep/$ds; C=$B/data/$ds.json ;; *) P=$O/prep-h/$ds; C=$H/data/$ds.json ;; esac
    say "Scoring E2 $m $ds"
    flock $LOCK $py examples/gemclean_bench_compare.py score "$P" "$C" "$O/opt/e2/$m" "$O/opt/e2/$m/score-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs "$ds-abs-minres-fast-j16" | cut -c1-120
  done
done
flock $LOCK $py - <<'EOF'
import json
from pathlib import Path
import numpy as np
root = Path("/mnt/d/rang/outputs/20261104-speed/opt/e1/single-1e4")
same = total = 0
for f in sorted((root / "rep1").glob("*-model.fits")):
    for kind in ("model", "residual"):
        a = (root / "rep1" / f.name.replace("model", kind)).read_bytes()
        for rep in (2, 3):
            total += 1
            same += a == (root / f"rep{rep}" / f.name.replace("model", kind)).read_bytes()
print(f"single-1e4 byte-identical across repeats: {same} of {total}")
EOF
say "E2 finished; nothing running."
