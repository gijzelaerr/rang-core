#!/bin/bash
# The private matched-state copy of E2-B's CASA MS for the J1833-2103
# measurement (research/gemclean-memory.md step 4): arm A5's a5_slim.py,
# unchanged, read-only on the source, into this task's output directory.
# Run in WSL; the caller wraps it in the main checkout's heavy_lock.py.
set -u
S=$(cd "$(dirname "$0")/../e2b-misses/a5-mask" && pwd)
R=/mnt/d/rang/outputs/e2-20261111-20-e2b
P=/mnt/d/rang/outputs/gemclean-memory-20261115
mkdir -p "$P/scripts"
cp "$S/a5_slim.py" "$P/scripts/"
rm -rf "$P/e2b-slim.ms"
s=$(date +%s)
docker run --rm --network none --user "$(id -u):$(id -g)" --tmpfs /tmp -e HOME=/tmp \
  -e OMP_NUM_THREADS=1 -v "$P:/p:rw" -v "$R/casa:/c:ro" -w /tmp rang-formats-oracle:20261030 \
  sh -c "/opt/qc/bin/python -I /p/scripts/a5_slim.py /c/e2b.ms /p/e2b-slim.ms /p/slim.json" > "$P/slim.out" 2>&1
rc=$?
echo "$(date -Is) slim rc=$rc secs=$(( $(date +%s) - s ))" >> "$P/runs.log"
exit $rc
