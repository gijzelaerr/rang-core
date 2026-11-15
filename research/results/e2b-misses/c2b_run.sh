#!/bin/bash
# 9.22's WSL steps; the caller wraps each in the main checkout's heavy_lock.py.
#   c2b_run.sh make       E on ext4 from a read-only mount of R/casa/e2b.ms
#   c2b_run.sh casa       CASA 6.7.6.14 applycal with 2b's spec, pointed at E
#   c2b_run.sh casa_done  rename CASA's columns, FLAG from the version again
#   c2b_run.sh copyout    plain cp -a of E to D:, sha256 of every file on both sides
#   c2b_run.sh drop       delete E
set -u
S=$(cd "$(dirname "$0")" && pwd)
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/e2b-2b-20261115
W=$HOME/e2b-2b
V=flags.rang_apply_20261112T013707Z
mkdir -p "$P" "$W/s"
cp "$S/c2b_e.py" "$W/s/"
fx() {  # formats container: /src (ro), /w (ext4)
  docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS=2 -v "$R/casa:/src:ro" -v "$W:/w:rw" -w /tmp rang-formats-oracle:20261030 \
    /opt/qc/bin/python -I /w/s/c2b_e.py "$@"
}
s=$(date +%s)
case "$1" in
  make)
    rm -rf "$W/e.ms"
    fx make /src/e2b.ms /w/e.ms /src/e2b.ms.flagversions/$V /w/make.json > "$P/make.out" 2>&1
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
    fx casa_done /w/e.ms /src/e2b.ms.flagversions/$V /w/casa_done.json > "$P/casa_done.out" 2>&1
    rc=$?; cp "$W/casa_done.json" "$P/" 2>/dev/null ;;
  copyout)
    rm -rf "$P/e2b-2b.ms"
    cp -a "$W/e.ms" "$P/e2b-2b.ms"; rc=$?
    if [ $rc = 0 ]; then
      (cd "$W/e.ms" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$P/e-ext4.sha256"
      (cd "$P/e2b-2b.ms" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$P/e-d.sha256"
      cmp "$P/e-ext4.sha256" "$P/e-d.sha256"; rc=$?
    fi ;;
  drop)
    rm -rf "$W/e.ms"; rc=$? ;;
esac
echo "$(date -Is) $* rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
