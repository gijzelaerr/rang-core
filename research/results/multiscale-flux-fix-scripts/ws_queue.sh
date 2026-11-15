#!/usr/bin/env bash
# Issue #23 step 4: WSClean 3.7 arms one after the other (Git Bash on Windows).
#   ws_queue.sh TAG WSL_FIELD WIN_FIELD WIN_ROOT ARM[:REPEAT]...
# Each run: examples/oracle_wsclean_clean.py in WSL on the ext4 field copy,
# under the main checkout's heavy_lock (4 slots, 3 GB); the model and MFS
# residual FITS, log and run.json are moved to WIN_ROOT/ws/ARM-rK/ and scored
# there by measure.py into WIN_ROOT/measures/TAG-ARM-rK.json.
set -u -o pipefail
tag=$1 wfield=$2 field=$3 root=$4
shift 4
lock=/c/Users/gijsm/Github/rang/tools/heavy_lock.py
py=/c/Users/gijsm/Github/rang/.venv/Scripts/python.exe
here=$(cd "$(dirname "$0")" && pwd)
wt=$(cd "$here/../../.." && pwd)
wsl_wt=/mnt/c/Users/gijsm/Worktrees/rang/ms-flux-fix
wsl_runs=/home/gijsm/msfix-20261116/ws-$tag
mkdir -p "$root/ws" "$root/measures"
for spec in "$@"; do
  arm=${spec%%:*} rep=1
  [ "$spec" != "$arm" ] && rep=${spec#*:}
  m=$root/measures/$tag-$arm-r$rep.json
  [ -e "$m" ] && continue
  out=$root/ws/$arm-r$rep
  if [ ! -e "$out/run.json" ]; then
    python "$lock" run --slots 4 --mem 3 -- wsl -e bash -lc \
      "mkdir -p $wsl_runs && rm -rf $wsl_runs/$arm-r$rep && python3 -I $wsl_wt/examples/oracle_wsclean_clean.py run $wfield $wsl_runs $arm --repeat $rep" \
      > "$root/ws/$arm-r$rep.out" 2>&1 || { echo "$arm r$rep: run failed"; continue; }
    mkdir -p "$out"
    wsl -e bash -lc "cd $wsl_runs/$arm-r$rep && cp run.json wsclean.log *-model.fits *-MFS-residual.fits /mnt/${out:1:1}${out:2} && cd .. && rm -rf $arm-r$rep" \
      || { echo "$arm r$rep: copy failed"; continue; }
  fi
  python "$lock" run --slots 4 --mem 2 -- "$py" "$here/measure.py" "$wt" "$field" \
    "$out" "$m" > "$root/measures/$tag-$arm-r$rep.out" 2>&1 || echo "$arm r$rep: measure failed"
  echo "$(date -Iseconds) $tag $arm r$rep done"
done
