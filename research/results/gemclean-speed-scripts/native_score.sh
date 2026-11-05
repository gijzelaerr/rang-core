#!/usr/bin/env bash
# Score the native pass (rep1, -j16, plus the plain loop on S1) and compare the repeats.
set -u
ROOT=/home/gijsm/Github/rang
N=/mnt/d/rang/outputs/20261104-speed/native
B=/mnt/d/rang/outputs/20261102-gemclean/bench
H=/mnt/d/rang/outputs/20261103-gemclean-heldout/sim
STATUS=/mnt/c/Users/gijsm/Github/rang/outputs/status/speed-run.md
SC=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/3a7c6dc0-f5f6-42d2-8618-88f7a313eb61/scratchpad
py=$ROOT/.venv/bin/python
mkdir -p "$N/scores"
cd "$ROOT" || exit 3
for ds in s1 s2 s3 h1 h2 h3 h4; do
  case $ds in s*) P=$B/prep/$ds; C=$B/data/$ds.json ;; *) P=$H/prep/$ds; C=$H/data/$ds.json ;; esac
  for im in wsclean gemclean; do
    { echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "Scoring the native pass: $im $ds"; } > "$STATUS"
    jobs=$(cd "$N/rep1/$im" && ls | grep "^$ds-.*j16-model.fits" | sed 's/-model.fits//')
    flock /home/gijsm/.rang-heavy.lock $py examples/gemclean_bench_compare.py score "$P" "$C" "$N/rep1/$im" "$N/scores/$im-$ds.json" \
      --timing-status "see research/gemclean-speed.md" --jobs $jobs
  done
done
flock /home/gijsm/.rang-heavy.lock $py "$SC/native_repeats.py" "$N"
{ echo "# speed-run status"; echo "Time: $(date '+%Y-%m-%d %H:%M %Z')"; echo "Native pass scored; nothing running."; } > "$STATUS"
echo finished
