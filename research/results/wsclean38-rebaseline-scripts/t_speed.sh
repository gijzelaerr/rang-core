#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Arm T of research/wsclean38-rebaseline.md: the speed table, WSClean 3.7 and 3.8 (glacier's
# native images) against GeMClean (6c615524), S1-S3 and H1-H4, -j 16 and -j 1, three repeats,
# then one run each of minres -mgain 0.9 and 0.95. Waits for 21:00; each job is one exclusive
# hold of the main checkout's heavy lock; no new block starts after 06:30. Run from WSL.
set -u
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
REPO=/mnt/c/Users/gijsm/Worktrees/rang/wsclean-38
LOCK=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
W=$HOME/Build/tmp/20261118-wsclean38-t
O=/mnt/d/rang/outputs/wsclean38-20261118/t
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/wsclean38.md
B=/mnt/d/rang/outputs/20261102-gemclean/bench/data
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data
SKIES="s1 s2 s3 h1 h2 h3 h4"
say() {
  { echo "# wsclean38 status (arm T)"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "$1"
    echo "Driver: research/results/wsclean38-rebaseline-scripts/t_speed.sh; outputs $O"; } > "$STATUS"
  echo "$(date -Is) $1"
}
late() {  # true from 06:30 until 21:00, the time no new block may start
  local hm; hm=$(date +%H%M); [ "$hm" -ge 0630 ] && [ "$hm" -lt 2100 ]
}
x() { python3 "$LOCK" run -- "$@"; }  # one exclusive hold
THREADS="16 1"; REPS="1 2 3"; MGAINS="0.9 0.95"
# SMOKE=1: a daytime check of this driver (S1, -j 16, one repeat, one -mgain cell, shared
# slots, no wait) into t-smoke; never scored.
if [ "${SMOKE:-0}" = 1 ]; then
  O=$O-smoke; W=$W-smoke; STATUS=/dev/null; SKIES=s1; THREADS=16; REPS=1; MGAINS=0.9
  x() { python3 "$LOCK" run --slots 8 --mem 12 -- "$@"; }
  late() { false; }
fi

while [ "${SMOKE:-0}" != 1 ] && [ "$(date +%H)" -lt 21 ]; do say "waiting for 21:00"; /usr/bin/sleep 300; done
mkdir -p "$W/data" "$O"
cp /mnt/d/rang/outputs/wsclean38-20261118/bin/gemclean-6c615524 "$W/gemclean"
for s in s1 s2 s3; do cp -r $B/$s.ms $B/$s.json "$W/data/"; done
for s in h1 h2 h3 h4; do cp -r $H/$s.ms $H/$s.json "$W/data/"; done
sha256sum "$W/gemclean" > "$O/gemclean.sha256"
for v in 3.7 3.8; do docker run --rm rang-wsclean-native:$v cat /wsclean-commit.txt > "$O/wsclean-$v-commit.txt"; done
export BENCH_DATA=$W/data BENCH_LOCK=$W/flock BENCH_MODES=abs
cd "$REPO" || exit 3

w() { BENCH_WSCLEAN_IMAGE=rang-wsclean-native:$1 BENCH_THREADS=$3 BENCH_LOOPS=fast BENCH_GRIDS="minres nominres" \
        x bash examples/gemclean_bench_run.sh wsclean "$4/w$1" "$2" | cut -c1-120; }
g() { BENCH_THREADS=$2 x bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$3/g" "$1" | cut -c1-120; }
gc() { GEMCLEAN_ARGS="-single -wgridder-accuracy 1e-4" BENCH_THREADS=$2 \
         x bash examples/gemclean_bench_gemclean.sh "$W/gemclean" "$3/gc" "$1" | cut -c1-120; }

for rep in $REPS; do
  if late; then say "06:30 reached before repeat $rep; stopped (protocol section 5)"; echo "STOPPED before rep $rep" >> "$O/notes.txt"; break; fi
  run=$W/out/rep$rep
  mkdir -p "$run"
  for ds in $SKIES; do
    for t in $THREADS; do
      say "repeat $rep of 3, $ds at -j $t"
      case $(( (rep - 1) % 4 )) in
        0) w 3.7 "$ds" "$t" "$run"; w 3.8 "$ds" "$t" "$run"; g "$ds" "$t" "$run"; gc "$ds" "$t" "$run" ;;
        1) w 3.8 "$ds" "$t" "$run"; g "$ds" "$t" "$run"; gc "$ds" "$t" "$run"; w 3.7 "$ds" "$t" "$run" ;;
        2) g "$ds" "$t" "$run"; gc "$ds" "$t" "$run"; w 3.7 "$ds" "$t" "$run"; w 3.8 "$ds" "$t" "$run" ;;
      esac
    done
  done
  rm -rf "$run"/*/ms
  cp -r "$run" "$O/" && rm -rf "$run"
  echo "repeat $rep done $(date -Is)" >> "$O/notes.txt"
done

for m in $MGAINS; do
  if late; then say "06:30 reached before -mgain $m; stopped"; echo "STOPPED before mgain $m" >> "$O/notes.txt"; break; fi
  for ds in $SKIES; do
    for v in 3.7 3.8; do
      say "-mgain $m, $ds, WSClean $v"
      BENCH_WSCLEAN_ARGS="-mgain $m" BENCH_WSCLEAN_IMAGE=rang-wsclean-native:$v BENCH_THREADS="$THREADS" \
        BENCH_LOOPS=fast BENCH_GRIDS=minres x bash examples/gemclean_bench_run.sh wsclean "$W/out/mgain$m/w$v" "$ds" | cut -c1-120
    done
  done
  rm -rf "$W/out/mgain$m"/*/ms
  cp -r "$W/out/mgain$m" "$O/" && rm -rf "$W/out/mgain$m"
  echo "mgain $m done $(date -Is)" >> "$O/notes.txt"
done
rm -rf "$W"
say "arm T finished; score with t_score.py"
echo "finished $(date -Is)" >> "$O/notes.txt"
