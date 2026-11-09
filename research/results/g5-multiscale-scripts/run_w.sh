#!/usr/bin/env bash
# run_w.sh RUN : WSClean 3.7 (rang-wsclean-native:3.7) on a run of cfg.sh at the protocol's
# settings, GNU time -v inside the container, into $O/runs/wsclean/RUN/w-*.
set -u
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
run=$1; shift
run_args "$run" || exit 2
d=$O/runs/wsclean/$run
rm -rf "$d"; mkdir -p "$d/tmp"
data=$(dirname "$ms"); name=$(basename "$ms")
exec 9>"$HOME/.rang-heavy.lock"
flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$d/load.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 \
  -v "$data:/data:ro" -v "$d:/run" -w /run rang-wsclean-native:3.7 \
  /usr/bin/time -v -o /run/time.txt \
  wsclean -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I \
  -no-update-model-required -temp-dir /run/tmp "${BASE[@]}" "${c[@]}" "$@" -name /run/w "/data/$name" > "$d/log.txt" 2>&1 9>&-
rc=$?
{ date -Iseconds; cat /proc/loadavg; } >> "$d/load.txt"
flock -u 9
rmdir "$d/tmp" 2>/dev/null
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time.txt")
printf '%s\t%s\t%s\t%s\t%s\t%s\n' wsclean "$run" "$rc" "$wall" "$rss" rang-wsclean-native:3.7 >> "$O/runs.tsv"
echo "wsclean $run rc=$rc wall=$wall maxrss_kB=$rss"
exit $rc
