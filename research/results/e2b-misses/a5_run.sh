#!/bin/bash
# Arm A5 in WSL (research/e2b-misses.md 9.18 and its amendment). The caller
# wraps each heavy step in the main checkout's heavy_lock.py, from the WSL side.
#   a5_run.sh slim                          private matched-state copy of R/casa/e2b.ms -> $P/e2b-slim.ms
#   a5_run.sh ext4                          copy $P/e2b-slim.ms to WSL ext4 ($X), byte for byte (no lock: a file copy)
#   a5_run.sh wsclean FID TAG mask|nomask   WSClean 3.7 cleaned, -no-small-inversion, reads $X -> $P/wsclean-<m>/TAG
#   a5_run.sh m0                            M0's WSClean run on G9's P1 -> $P/m0/wsclean
set -u
S=$(cd "$(dirname "$0")" && pwd)
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/gemclean-iquv-mask-20261115
X=$HOME/Build/tmp/20261115-gemclean-iquv-mask
mkdir -p "$P/scripts" "$X"
cp "$S/a5_slim.py" "$P/scripts/"
dk() {  # image, threads, extra mounts, command
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS="$2" -v "$P:/p:rw" $3 -w /tmp "$1" sh -c "$4"
}
s=$(date +%s)
case "$1" in
  slim)
    rm -rf "$P/e2b-slim.ms"
    dk rang-formats-oracle:20261030 1 "-v $R/casa:/c:ro" \
      "/opt/qc/bin/python -I /p/scripts/a5_slim.py /c/e2b.ms /p/e2b-slim.ms /p/slim.json" > "$P/slim.out" 2>&1
    rc=$? ;;
  flagcat)  # WSClean needs FLAG_CATEGORY (added to the ext4 copy only, empty, as in the source)
    cp "$S/a5_flagcat.py" "$P/scripts/"
    dk rang-formats-oracle:20261030 1 "-v $R/casa:/c:ro -v $X:/x:rw"       "/opt/qc/bin/python -I /p/scripts/a5_flagcat.py /c/e2b.ms /x/e2b-slim.ms /p/flagcat.json" > "$P/flagcat.out" 2>&1
    rc=$? ;;
  ext4)
    rm -rf "$X/e2b-slim.ms"; cp -a "$P/e2b-slim.ms" "$X/"
    (cd "$P/e2b-slim.ms" && find . -type f -exec sha256sum {} + | sort -k2) > "$X/d.sha"
    (cd "$X/e2b-slim.ms" && find . -type f -exec sha256sum {} + | sort -k2) > "$X/x.sha"
    cmp "$X/d.sha" "$X/x.sha"; rc=$?; cp "$X/x.sha" "$P/slim-ext4.sha256" ;;
  wsclean)
    fid=$2; tag=$3; m=$4; extra=""
    [ "$m" = mask ] && extra="-auto-mask 5"
    out=/p/wsclean-$m/$tag; tmp=/x/tmp-$m-$tag
    mkdir -p "$P/wsclean-$m/$tag" "$X/tmp-$m-$tag"
    dk rang-wsclean-native:3.7 4 "-v $X:/x:rw" "/usr/bin/time -v -o $out.time.txt wsclean -name $out/$tag-clean \
      -size 2048 2048 -scale 2asec -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV \
      -join-polarizations -data-column RANG_CORRECTED_DATA -gridder wgridder -wgridder-accuracy 0.0001 \
      -no-update-model-required -no-small-inversion -j 4 -temp-dir $tmp -niter 1000000 -mgain 0.9 \
      -auto-threshold 3.0 $extra -field $fid /x/e2b-slim.ms" > "$P/wsclean-$m/$tag.out" 2>&1
    rc=$?; rm -rf "$X/tmp-$m-$tag" ;;
  m0)
    mkdir -p "$P/m0/wsclean/tmp"
    dk rang-wsclean-native:3.7 4 "-v /mnt/d/rang/outputs/g9-20261107-02/data:/data:ro" \
      "/usr/bin/time -v -o /p/m0/wsclean.time.txt wsclean -gridder wgridder -no-min-grid-resolution \
      -no-small-inversion -wgridder-accuracy 1e-6 -mgain 0.8 -no-update-model-required \
      -temp-dir /p/m0/wsclean/tmp -size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 \
      -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 4 -pol IQUV -join-polarizations \
      -channels-out 8 -join-channels -auto-threshold 3 -auto-mask 5 -name /p/m0/wsclean/w /data/P1.ms" \
      > "$P/m0/wsclean.out" 2>&1
    rc=$?; rm -rf "$P/m0/wsclean/tmp" ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
