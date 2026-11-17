#!/bin/bash
# 9.18 in WSL; the caller wraps each call in the main checkout's heavy_lock.py.
#   a5_run.sh copy                      reduced copy of R/casa/e2b.ms -> ~/e2b-close/a5.ms (ext4)
#   a5_run.sh wsclean MODE FID TAG EPS  MODE default|nosi, -j 2, reading the ext4 copy
#   a5_run.sh drop                      delete the ext4 copy
set -u
S=$(cd "$(dirname "$0")" && pwd)
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/e2b-close-20261115/a5
W=$HOME/e2b-close
mkdir -p "$P" "$W"
s=$(date +%s)
case "$1" in
  copy)
    cp "$S/a5_copy.py" "$W/"
    rm -rf "$W/a5.ms"
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
      -e OMP_NUM_THREADS=1 -v "$R/casa:/c:ro" -v "$W:/w:rw" -w /tmp rang-formats-oracle:20261030 \
      /opt/qc/bin/python -I /w/a5_copy.py /c/e2b.ms /w/a5.ms /w/a5-copy.json > "$P/copy.out" 2>&1
    rc=$?; cp "$W/a5-copy.json" "$P/" 2>/dev/null; du -sh "$W/a5.ms" >> "$P/copy.out" ;;
  wsclean)
    mode=$2; fid=$3; tag=$4; eps=$5; extra=""
    [ "$mode" = nosi ] && extra=-no-small-inversion
    out=/p/$mode/$tag-eps$eps
    mkdir -p "$P/$mode/$tag-eps$eps" "$W/tmp/$mode-$tag-$eps"
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
      -e OMP_NUM_THREADS=2 -v "$W:/c:rw" -v "$P:/p:rw" -w /tmp rang-wsclean-native:3.7 sh -c \
      "wsclean -name $out/$tag-dirty -size 2048 2048 -scale 2asec \
      -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
      -data-column RANG_CORRECTED_DATA -gridder wgridder -wgridder-accuracy $eps \
      -no-update-model-required -j 2 -temp-dir /c/tmp/$mode-$tag-$eps -niter 0 $extra -field $fid /c/a5.ms" \
      > "$P/$mode/$tag-eps$eps.out" 2>&1
    rc=$?; rm -rf "$W/tmp/$mode-$tag-$eps" ;;
  fixcat)
    cp "$S/a5_fixcat.py" "$W/"
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp       -v "$R/casa:/c:ro" -v "$W:/w:rw" -w /tmp rang-formats-oracle:20261030       /opt/qc/bin/python -I /w/a5_fixcat.py /c/e2b.ms /w/a5.ms > "$P/fixcat.out" 2>&1
    rc=$? ;;
  drop)
    rm -rf "$W/a5.ms"; rc=$? ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
