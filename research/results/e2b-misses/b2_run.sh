#!/bin/bash
# 9.19's WSL steps; the caller wraps each in the main checkout's heavy_lock.py.
#   b2_run.sh cols ARGS...   b2_cols.py on R/casa/e2b.ms (formats container)
#   b2_run.sh casa           CASA 6.7.6.14 applycal with 2b's own spec (R/applycal-spec.json)
set -u
S=$(cd "$(dirname "$0")" && pwd)
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/e2b-close-20261115/b2
mkdir -p "$P/scripts"
cp "$S/b2_cols.py" "$R/e2p_applycal.py" "$P/scripts/"
dk() {  # image, command
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=2 -v "$R/casa:/c:rw" -v "$R:/r:ro" -v "$P:/b:rw" -w /tmp "$1" sh -c "$2"
}
s=$(date +%s)
case "$1" in
  cols)
    shift; args=$(printf ' %q' "$@")
    dk rang-formats-oracle:20261030 "/opt/qc/bin/python -I /b/scripts/b2_cols.py /c/e2b.ms$args" \
      > "$P/cols-$1.out" 2>&1
    rc=$? ;;
  casa)
    # 2b's spec names /c/e2b.ms and /p/rang-run/calibrate: mount R at /p as 2b did
    docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
      -e OMP_NUM_THREADS=2 -v "$R/casa:/c:rw" -v "$R:/p:ro" -v "$P:/b:rw" -w /tmp \
      rang-o-casa:6.7.6.14 sh -c "/opt/casa/bin/python -I /b/scripts/e2p_applycal.py /p/applycal-spec.json /b/casa-result.json; cp /tmp/casa-*.log /b/ 2>/dev/null; true" \
      > "$P/casa.out" 2>&1
    rc=$?; grep -q '"error": null' "$P/casa-result.json" && ! grep -q '"error": "' "$P/casa-result.json" || rc=3 ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
