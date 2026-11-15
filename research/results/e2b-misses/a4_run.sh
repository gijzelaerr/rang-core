#!/bin/bash
# Arm A4 in WSL (research/e2b-misses.md 9.9). The caller wraps each call in
# the main checkout's heavy_lock.py.
#   a4_run.sh unit on|off            gate 3c's matched state on R/casa/e2b.ms
#   a4_run.sh wsclean FID TAG EPS    WSClean 3.7 dirty image -> $P/a4/wsclean/TAG-eps<EPS>
set -u
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/e2b-pastro-20261114
S=/mnt/c/Users/gijsm/Worktrees/rang/e2b-pastro/research/results/e2b-misses
mkdir -p "$P/a4/wsclean" "$P/a4/scripts"
cp "$S/a4_unit.py" "$P/a4/scripts/"
dk() {  # image, threads, command
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS="$2" -v "$R/casa:/c:rw" -v "$P/a4:/p:rw" -w /tmp "$1" sh -c "$3"
}
s=$(date +%s)
case "$1" in
  unit)
    dk rang-formats-oracle:20261030 1 "/opt/qc/bin/python -I /p/scripts/a4_unit.py /c/e2b.ms $2 /p/unit-$2.json"
    rc=$? ;;
  wsclean)
    fid=$2; tag=$3; eps=$4; out=/p/wsclean/$tag-eps$eps
    mkdir -p "$P/a4/wsclean/$tag-eps$eps/tmp"
    dk rang-wsclean-native:3.7 4 "wsclean -name $out/$tag-dirty -size 2048 2048 -scale 2asec \
      -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
      -data-column RANG_CORRECTED_DATA -gridder wgridder -wgridder-accuracy $eps \
      -no-update-model-required -j 4 -temp-dir $out/tmp -niter 0 -field $fid /c/e2b.ms" \
      > "$P/a4/wsclean/$tag-eps$eps.out" 2>&1
    rc=$?; rm -rf "$P/a4/wsclean/$tag-eps$eps/tmp" ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/a4/runs.log"
exit $rc
