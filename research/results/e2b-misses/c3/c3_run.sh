#!/bin/bash
# e2b-misses 9.28's WSL steps; the caller wraps each in the main checkout's heavy_lock.py.
#   c3_run.sh make                E on ext4 from a read-only mount of e3-20261111-input/e2b.ms
#   c3_run.sh casa                CASA 6.7.6.14 applycal with 2b's spec, pointed at E
#   c3_run.sh casa_done           rename CASA's columns, FLAG from the frozen flags again
#   c3_run.sh filehash            sha256 of every file of E (against c2b/e-ext4.sha256, reported)
#   c3_run.sh subset FID          field FID's rows of E -> $W/s<FID>.ms, WEIGHT = 1
#   c3_run.sh copyout FID         cp -a $W/s<FID>.ms to D:, sha256 of every file on both sides
#   c3_run.sh copyback FID        cp -a the D: copy (after rang's apply) to $W/f<FID>.ms, sha256 both sides
#   c3_run.sh compare FID         2b's rule, E's CASA columns against f<FID>.ms's rang columns
#   c3_run.sh wsclean dirty|clean FID TAG   gate 3c's WSClean 3.7 arm, reading $W/f<FID>.ms
#   c3_run.sh dropf FID | drope   delete ext4 copies
set -u
S=$(cd "$(dirname "$0")" && pwd)
E3=/mnt/d/rang/outputs/e3-20261111-input
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/e2b-confirm-20261116
W=$HOME/Build/tmp/20261116-e2b-confirm
mkdir -p "$P" "$W/s"
cp "$S/c3_e.py" "$W/s/"
fx() {  # formats container: /src (ro e3 input), /w (ext4)
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=2 -v "$E3:/src:ro" -v "$W:/w:rw" -w /tmp rang-formats-oracle:20261030 \
    /opt/qc/bin/python -I /w/s/c3_e.py "$@"
}
shas() { (cd "$1" && find . -type f -print0 | sort -z | xargs -0 sha256sum); }
s=$(date +%s)
case "$1" in
  make)
    cp "$P/rang-flag-after-apply.npy" "$W/flags.npy"
    rm -rf "$W/e.ms"
    fx make /src/e2b.ms /w/e.ms /w/flags.npy /w/make.json > "$P/make.out" 2>&1
    rc=$?; cp "$W/make.json" "$P/" 2>/dev/null ;;
  casa)
    python3 - "$R/applycal-spec.json" "$W/spec.json" <<'EOF'
import json, sys
spec = json.load(open(sys.argv[1]))
for c in spec:
    assert c["vis"] == "/c/e2b.ms"
    c["vis"] = "/w/e.ms"
    c["gaintable"] = [g.replace("/p/rang-run/calibrate", "/w/tables") for g in c["gaintable"]]
    assert all(g.startswith("/w/tables/") for g in c["gaintable"])
json.dump(spec, open(sys.argv[2], "w"), indent=1)
EOF
    cp "$R/e2p_applycal.py" "$W/s/"; rm -f "$W/casa-result.json"
    rm -rf "$W/tables"; cp -a "$R/rang-run/calibrate" "$W/tables"  # small; CASA locks tables it reads
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
      -e OMP_NUM_THREADS=2 -v "$R:/p:ro" -v "$W:/w:rw" -w /tmp rang-o-casa:6.7.6.14 sh -c \
      "/opt/casa/bin/python -I /w/s/e2p_applycal.py /w/spec.json /w/casa-result.json; cp /tmp/casa-*.log /w/ 2>/dev/null; true" \
      > "$P/casa.out" 2>&1
    cp "$W/casa-result.json" "$W"/casa-*.log "$P/" 2>/dev/null
    rc=0; grep -q '"error": "' "$W/casa-result.json" && rc=3; [ -f "$W/casa-result.json" ] || rc=4 ;;
  casa_done)
    fx casa_done /w/e.ms /src/e2b.ms /w/flags.npy /w/casa_done.json > "$P/casa_done.out" 2>&1
    rc=$?; cp "$W/casa_done.json" "$P/" 2>/dev/null ;;
  filehash)
    shas "$W/e.ms" > "$P/e-ext4.sha256"; rc=$? ;;
  subset)
    f=$2; rm -rf "$W/s$f.ms"
    fx subset /w/e.ms "$f" "/w/s$f.ms" "/w/subset$f.json" > "$P/subset$f.out" 2>&1 \
      && fx unitw "/w/s$f.ms" "/w/unitw$f.json" >> "$P/subset$f.out" 2>&1
    rc=$?; cp "$W/subset$f.json" "$W/unitw$f.json" "$P/" 2>/dev/null ;;
  copyout)
    f=$2; rm -rf "$P/f$f.ms"
    cp -a "$W/s$f.ms" "$P/f$f.ms"; rc=$?
    if [ $rc = 0 ]; then
      shas "$W/s$f.ms" > "$P/s$f-ext4.sha256"; shas "$P/f$f.ms" > "$P/s$f-d.sha256"
      cmp "$P/s$f-ext4.sha256" "$P/s$f-d.sha256"; rc=$?
    fi
    [ $rc = 0 ] && rm -rf "$W/s$f.ms" ;;
  copyback)
    f=$2; rm -rf "$W/f$f.ms"
    cp -a "$P/f$f.ms" "$W/f$f.ms"; rc=$?
    if [ $rc = 0 ]; then
      shas "$P/f$f.ms" > "$P/f$f-d.sha256"; shas "$W/f$f.ms" > "$P/f$f-ext4.sha256"
      cmp "$P/f$f-d.sha256" "$P/f$f-ext4.sha256"; rc=$?
    fi ;;
  compare)
    f=$2
    fx compare /w/e.ms "/w/f$f.ms" "$f" /w/flags.npy "/w/g2b-f$f.json" > "$P/compare$f.out" 2>&1
    rc=$?; cp "$W/g2b-f$f.json" "$P/" 2>/dev/null ;;
  wsclean)
    m=$2; f=$3; tag=$4
    if [ "$m" = dirty ]; then
      extra="-niter 0 -wgridder-accuracy 1e-06 -j 2"; out=/p/wsclean-dirty/$tag
    else
      extra="-niter 1000000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001 -j 4"
      out=/p/wsclean-clean/$tag
    fi
    name=$tag-$m; [ "$m" = clean ] && name=$tag-clean
    mkdir -p "$P/wsclean-$m/$tag" "$W/tmp-$m-$tag"
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
      -e OMP_NUM_THREADS=4 -v "$W:/x:rw" -v "$P:/p:rw" -w /tmp rang-wsclean-native:3.7 sh -c \
      "/usr/bin/time -v -o $out.time.txt wsclean -name $out/$name -size 2048 2048 -scale 2asec \
      -weight briggs 0.0 -channels-out 8 -join-channels -pol IQUV -join-polarizations \
      -data-column E2C_RANG_CORRECTED_DATA -gridder wgridder -no-update-model-required \
      -no-small-inversion -temp-dir /x/tmp-$m-$tag $extra -field $f /x/f$f.ms" \
      > "$P/wsclean-$m/$tag.out" 2>&1
    rc=$?; rm -rf "$W/tmp-$m-$tag" ;;
  dropf)
    rm -rf "$W/f$2.ms" "$W/s$2.ms"; rc=$? ;;
  drope)
    rm -rf "$W/e.ms"; rc=$? ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
