#!/usr/bin/env bash
# Issue #23 step 4: run and score gemclean arms one after the other, each under
# the main checkout's heavy_lock (4 slots, 6 GB; scoring 4 slots, 2 GB).
#   gc_queue.sh FIELD_DIR OUT_ROOT TAG ARM...      (Git Bash on Windows)
# One OUT_ROOT per field; the binary is $BIN or OUT_ROOT/../bin/gemclean.exe.
# Writes OUT_ROOT/gc/ARM-r1/ and OUT_ROOT/measures/TAG-ARM-r1.json; skips an
# arm whose measure file exists. FLOOR=path adds the reducible fraction.
set -u -o pipefail
field=$1 root=$2 tag=$3
shift 3
lock=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
py=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
here=$(cd "$(dirname "$0")" && pwd)
wt=$(cd "$here/../../.." && pwd)
bin=${BIN:-$root/../bin/gemclean.exe}
mkdir -p "$root/gc" "$root/measures"
for arm in "$@"; do
  m=$root/measures/$tag-$arm-r1.json
  [ -e "$m" ] && continue
  if [ ! -e "$root/gc/$arm-r1/run.json" ]; then
    rm -rf "$root/gc/$arm-r1"
    python "$lock" run --slots 4 --mem 6 -- "$py" "$here/run_gc.py" "$bin" "$field" \
      "$root/gc" "$arm" 1 > "$root/gc/$arm-r1.out" 2>&1 || { echo "$arm: run failed"; continue; }
  fi
  extra=()
  [ -n "${FLOOR:-}" ] && extra=(--floor "$FLOOR")
  python "$lock" run --slots 4 --mem 2 -- "$py" "$here/measure.py" "$wt" "$field" \
    "$root/gc/$arm-r1" "$m" "${extra[@]}" > "$root/measures/$tag-$arm-r1.out" 2>&1 \
    || { echo "$arm: measure failed"; continue; }
  # Scored: keep the model cube and the MFS residual, delete the other images.
  ( cd "$root/gc/$arm-r1" && rm -f -- *-dirty.fits *-image.fits *-psf.fits \
      *-[0-9][0-9][0-9][0-9]-residual.fits )
  echo "$(date -Iseconds) $tag $arm done"
done
