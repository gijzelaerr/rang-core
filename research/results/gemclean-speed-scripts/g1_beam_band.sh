#!/usr/bin/env bash
# G1: -beam-band on and off with one binary built at a recorded commit, interleaved, paired.
# Timed: S1, H2, H3 at -j 16 and -j 1, 8 repeats, order alternating by repeat, plus extra pairs for
# pairs a busy host spoiled. Images only: S2, S3, H1, H4 at -j 16, one pair each. Then scoring and
# the rule of research/gemclean-speed.md, applied by g1_beam_band_analyse.py.
# Usage: bash g1_beam_band.sh  (from anywhere; the worktree must be clean)
set -u
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
BASE=/mnt/d/rang/outputs/20261104-speed
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
OUT=/mnt/d/rang/outputs/20261105-g1-beam-band
W=$HOME/Build/tmp/20261105-g1-beam-band
LOCK=$HOME/.rang-heavy.lock
STATUS=$HOME/Github/rang/outputs/status/fp-g1.md
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
py=$ROOT/.venv/bin/python
REPEATS=8
EXTRA_MAX=4
BIN=$W/gemclean

say() {
  { echo "# fp-g1 status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"
    echo "State: $1"; echo "Next: finish the driver, apply the committed rule, act on it."
    echo "Log: $OUT/driver.log"; } > "$STATUS"
  echo "$(date '+%H:%M:%S') $1"
}

busy() { # label: processes above 50 % of one core, WSL then Windows
  echo "== $1 $(date -Iseconds) WSL"
  top -b -n 2 -d 1 -c -w 200 | awk '/^top - /{n++} n==2 && $1 ~ /^[0-9]+$/ && $9+0 > 50'
  echo "== $1 Windows"
  timeout 20 "$PS" -NoProfile -Command \
    'Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $_.PercentProcessorTime -gt 50 -and $_.Name -notmatch "^(_Total|Idle)$" } | ForEach-Object { "$($_.PercentProcessorTime) $($_.Name)" }' \
    2>/dev/null | tr -d '\r' || echo "(not available)"
}

# The probe's own processes (WmiPrvSE, top) and the WSL VM (vmmem; what runs in it is listed by top) do not count.
flagged() {
  if sed -e '/^==/d' "$1" | grep -v -i -e wmiprvse -e 'top -b' -e vmmem -e '(not available)' -e '^$' | grep -q .; then
    echo 1
  else
    echo 0
  fi
}

one() { # sky j flag(on|off) rep keep(1|0)
  local sky=$1 j=$2 flag=$3 rep=$4 keep=$5 size=2048 opt="" n
  [ "$sky" = h3 ] && size=4096
  [ "$flag" = on ] && opt=-beam-band
  n=$sky-j$j-$flag-r$rep
  exec 9>"$LOCK"
  flock 9
  busy before > "$OUT/load/$n.busy.txt" 9>&-
  sleep 3
  cat /proc/loadavg > "$OUT/load/$n.txt"
  /usr/bin/time -f "$n wall %e user %U sys %S rss_kb %M" "$BIN" -name "$W/$n" -size "$size" "$size" -scale 1.5asec \
    -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j "$j" \
    -single -wgridder-accuracy 1e-4 $opt "$W/$sky.ms" > "$OUT/logs/$n.log" 2>&1 9>&-
  local rc=$?
  cat /proc/loadavg >> "$OUT/load/$n.txt"
  busy after >> "$OUT/load/$n.busy.txt" 9>&-
  flock -u 9
  exec 9>&-
  [ $rc -eq 0 ] || { say "FAILED $n exit $rc"; exit 5; }
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$n" "$sky" "$j" "$flag" "$rep" \
    "$(flagged "$OUT/load/$n.busy.txt")" "$(tail -1 "$OUT/logs/$n.log")" >> "$OUT/runs.tsv"
  (cd "$W" && sha256sum "$n-model.fits" "$n-residual.fits" "$n-image.fits") >> "$OUT/sha256.txt"
  if [ "$keep" = 1 ]; then
    mv "$W/$n-model.fits" "$W/$n-residual.fits" "$W/$n-image.fits" "$OUT/images/"
    cp "$OUT/logs/$n.log" "$OUT/images/"
  fi
  rm -f "$W/$n"-*.fits "$W/$n"-*.json
  tail -1 "$OUT/logs/$n.log" | cut -c1-90
}

pair() { # sky j rep keep first
  if [ "$5" = off ]; then
    one "$1" "$2" off "$3" "$4"; one "$1" "$2" on "$3" "$4"
  else
    one "$1" "$2" on "$3" "$4"; one "$1" "$2" off "$3" "$4"
  fi
}

clean_pairs() { # sky j: repeats where both runs have flag 0 in runs.tsv
  awk -F'\t' -v s="$1" -v j="$2" '$2==s && $3==j { n[$5]++; b[$5]+=$6 } END { c=0; for (r in n) if (n[r]==2 && b[r]==0) c++; print c }' "$OUT/runs.tsv"
}

[ -e "$OUT/runs.tsv" ] && { echo "$OUT/runs.tsv exists; refusing to mix runs"; exit 2; }
cd "$ROOT" || exit 3
[ -z "$(git status --porcelain)" ] || { echo "worktree not clean"; exit 3; }
mkdir -p "$OUT/logs" "$OUT/load" "$OUT/images" "$OUT/scores" "$W"
COMMIT=$(git rev-parse HEAD)
say "building at $COMMIT"
(cd core && flock "$LOCK" cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -1)
cp core/target/gemclean/gemclean "$OUT/gemclean-${COMMIT:0:12}"
cp core/target/gemclean/gemclean "$BIN"
{ echo "commit $COMMIT"; rustc +1.93 -V; echo "profile gemclean, target-cpu x86-64-v3 from core/.cargo/config.toml"
  sha256sum "$BIN"; uname -r; nproc; date -Iseconds; } | tee "$OUT/provenance.txt"
for s in s1 s2 s3; do cp -r "$B/data/$s.ms" "$W/"; done
for s in h1 h2 h3 h4; do cp -r "$H/data/$s.ms" "$W/"; done

# Flag off must still be the image of 3945394, or the baseline has moved.
say "gate: flag off on S1 against 3945394"
one s1 16 off gate 1
for k in model residual; do
  cmp "$OUT/images/s1-j16-off-rgate-$k.fits" "$BASE/opt/e1/single-1e4/rep1/s1-abs-nominres-fast-j16-$k.fits" \
    || { say "GATE FAILED: $k differs from 3945394"; exit 4; }
done
echo "gate passed: model and residual byte-identical to 3945394" | tee -a "$OUT/provenance.txt"
# The gate is not a timing pair.
sed -i '/-rgate\t\|\tgate\t/d' "$OUT/runs.tsv"

for r in $(seq 1 $REPEATS); do
  for s in s1 h2 h3; do
    for j in 16 1; do
      say "timing repeat $r of $REPEATS, $s -j $j"
      keep=0; [ "$r" = 1 ] && keep=1
      if ((r % 2)); then pair $s $j "$r" $keep off; else pair $s $j "$r" $keep on; fi
    done
  done
done

# A spoiled pair gets a replacement at the end, up to EXTRA_MAX per cell; both are reported.
for s in s1 h2 h3; do
  for j in 16 1; do
    x=0
    while [ "$(clean_pairs $s $j)" -lt $REPEATS ] && [ $x -lt $EXTRA_MAX ]; do
      x=$((x + 1))
      say "replacement pair $x, $s -j $j"
      if ((x % 2)); then pair $s $j "x$x" 0 off; else pair $s $j "x$x" 0 on; fi
    done
  done
done

for s in s2 s3 h1 h4; do
  say "image pair $s -j 16"
  pair $s 16 1 1 off
done
{ echo "finished timing $(date -Iseconds)"; cat /proc/loadavg; } >> "$OUT/provenance.txt"
rm -f "$W"/*.fits
rm -rf "$W"

for s in s1 s2 s3 h1 h2 h3 h4; do
  say "scoring $s"
  case $s in
    s*) P=$B/prep/$s; C=$B/data/$s.json ;;
    *) P=$BASE/prep-h/$s; C=$H/data/$s.json ;;
  esac
  jobs="$s-j16-off-r1 $s-j16-on-r1"
  case $s in s1 | h2 | h3) jobs="$jobs $s-j1-off-r1 $s-j1-on-r1" ;; esac
  # shellcheck disable=SC2086
  flock "$LOCK" "$py" examples/gemclean_bench_compare.py score "$P" "$C" "$OUT/images" "$OUT/scores/$s.json" \
    --timing-status "see research/gemclean-speed.md" --jobs $jobs | cut -c1-120
done
"$py" research/results/gemclean-speed-scripts/g1_beam_band_analyse.py "$OUT" research/results/gemclean-beam-band.json
say "driver finished; nothing running. Apply the verdict."
