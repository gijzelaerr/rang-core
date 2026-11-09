#!/usr/bin/env bash
# run_g.sh OUT BIN SKY CFG : GeMClean (binary BIN) at the rule's settings, under the heavy lock,
# GNU time -v. Files g-*; a line in OUT/runs.tsv with the binary's sha256 prefix.
set -u
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
O=$1; B=$2; sky=$3; cfg=$4
cfg_args "$cfg" || exit 2
ms=$(data_of "$sky") || exit 2
d=$O/runs/g/$sky-$cfg
rm -rf "$d"; mkdir -p "$d"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$d/load.txt"
/usr/bin/time -v -o "$d/time.txt" "$B" "${BASE[@]}" "${c[@]}" -name "$d/g" "$ms" > "$d/log.txt" 2>&1 9>&-
rc=$?
{ date -Iseconds; cat /proc/loadavg; } >> "$d/load.txt"
flock -u 9
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time.txt")
sha=$(sha256sum "$B" | cut -c1-12)
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' gemclean "$sky" "$cfg" "$rc" "$wall" "$rss" "$sha" >> "$O/runs.tsv"
echo "gemclean $sky-$cfg rc=$rc wall=$wall maxrss_kB=$rss"
