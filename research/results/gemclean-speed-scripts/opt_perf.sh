#!/usr/bin/env bash
# Where GeMClean coarse spends its time at -j 1 and -j 16, S1 and H3.
set -u
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
O=/mnt/d/rang/outputs/20261104-speed
W=/home/gijsm/Build/tmp/20261104-perf
mkdir -p "$W"
cp -r /mnt/d/rang/outputs/20261102-gemclean/bench/data/s1.ms "$W/"
cp -r /mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data/h3.ms "$W/"
which perf || ls /usr/lib/linux-tools*/perf
PERF=$(which perf || ls /usr/lib/linux-tools*/perf | head -1)
run() { # ds size j
  flock /home/gijsm/.rang-heavy.lock "$PERF" record -q -F 500 -g -o "$W/$1-j$3.data" -- "$O/gemclean-3945394" -name "$W/$1-j$3" -size "$2" "$2" -scale 1.5asec -weight briggs 0.5 \
    -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j "$3" -single -wgridder-accuracy 1e-4 "$W/$1.ms" > "$W/$1-j$3.log" 2>&1
  echo "== $1 j$3"
  "$PERF" report -i "$W/$1-j$3.data" --no-children --stdio --sort symbol -g none --percent-limit 1 2>/dev/null | grep -v '^#' | grep -v '^$' | cut -c1-110 | head -24
  tail -3 "$W/$1-j$3.log" | cut -c1-200
}
run s1 2048 1
run s1 2048 16
run h3 4096 1
rm -rf "$W"
