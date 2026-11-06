#!/usr/bin/env bash
# run_g.sh BIN TAG SKY CFG [extra]: one GeMClean run at the rule's settings, under the heavy lock, GNU time -v.
set -u
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
bin=$1; tag=$2; sky=$3; cfg=$4; shift 4
cfg_args "$cfg" || exit 2
d=$O/runs/$tag/$sky-$cfg
rm -rf "$d"; mkdir -p "$d"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$d/load.txt"
/usr/bin/time -v -o "$d/time.txt" "$bin" -name "$d/g" "${BASE[@]}" "${c[@]}" "$@" "$O/data/$sky.ms" > "$d/log.txt" 2>&1 9>&-
rc=$?
{ date -Iseconds; cat /proc/loadavg; } >> "$d/load.txt"
flock -u 9
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time.txt")
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$sky" "$cfg" "$rc" "$wall" "$rss" "$(sha256sum "$bin" | cut -c1-12)" >> "$O/runs.tsv"
echo "$tag $sky-$cfg rc=$rc wall=$wall maxrss_kB=$rss"
