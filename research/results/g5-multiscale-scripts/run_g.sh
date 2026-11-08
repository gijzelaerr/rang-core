#!/usr/bin/env bash
# run_g.sh BIN TAG RUN [extra]: one GeMClean run of cfg.sh under the heavy lock, GNU time -v,
# into $O/runs/TAG/RUN/g-*. Stops the run if its RSS passes 24e9 bytes.
set -u
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
bin=$1; tag=$2; run=$3; shift 3
run_args "$run" || exit 2
d=$O/runs/$tag/$run
rm -rf "$d"; mkdir -p "$d"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$d/load.txt"
/usr/bin/time -v -o "$d/time.txt" "$bin" -name "$d/g" "${BASE[@]}" "${c[@]}" "$@" "$ms" > "$d/log.txt" 2>&1 9>&- &
pid=$!
# The watchdog: stop at 24e9 bytes of RSS (research/g5-multiscale.md, F).
while kill -0 $pid 2>/dev/null; do
  child=$(pgrep -P $pid gemclean | head -1)
  if [ -n "$child" ]; then
    kb=$(awk '/VmRSS/{print $2}' /proc/$child/status 2>/dev/null)
    if [ -n "$kb" ] && [ "$kb" -gt 23437500 ]; then
      echo "watchdog: RSS $kb kB, stopped" >> "$d/log.txt"; kill $child
    fi
  fi
  sleep 1
done
wait $pid
rc=$?
{ date -Iseconds; cat /proc/loadavg; } >> "$d/load.txt"
flock -u 9
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time.txt")
printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$run" "$rc" "$wall" "$rss" "$(sha256sum "$bin" | cut -c1-12)" >> "$O/runs.tsv"
echo "$tag $run rc=$rc wall=$wall maxrss_kB=$rss"
