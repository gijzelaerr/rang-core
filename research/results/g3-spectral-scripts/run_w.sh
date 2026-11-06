#!/usr/bin/env bash
# run_w.sh SKY CFG : WSClean 3.7 (rang-wsclean-native:3.7) at the rule's settings; GNU time -v inside the container.
set -u
here=$(dirname "$(readlink -f "$0")")
source "$here/cfg.sh"
sky=$1; cfg=$2
cfg_args "$cfg" || exit 2
# WSClean makes no PSF at -niter 0 unless asked.
case " ${c[*]} " in *" -niter 0 "*) c+=(-make-psf) ;; esac
d=$O/runs/wsclean/$sky-$cfg
rm -rf "$d"; mkdir -p "$d/tmp"
exec 9>"$HOME/.rang-heavy.lock"
flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$d/load.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 \
  -v "$O/data:/data:ro" -v "$d:/run" -w /run rang-wsclean-native:3.7 \
  /usr/bin/time -v -o /run/time.txt \
  wsclean -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -mgain 0.8 -pol I -nmiter 0 \
  -no-update-model-required -temp-dir /run/tmp "${BASE[@]}" "${c[@]}" -name /run/w "/data/$sky.ms" > "$d/log.txt" 2>&1 9>&-
rc=$?
{ date -Iseconds; cat /proc/loadavg; } >> "$d/load.txt"
flock -u 9
rmdir "$d/tmp" 2>/dev/null
rss=$(awk -F': ' '/Maximum resident/{print $2}' "$d/time.txt")
wall=$(awk -F': ' '/Elapsed/{print $2}' "$d/time.txt")
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' wsclean "$sky" "$cfg" "$rc" "$wall" "$rss" rang-wsclean-native:3.7 >> "$O/runs.tsv"
echo "wsclean $sky-$cfg rc=$rc wall=$wall maxrss_kB=$rss"
