#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# TS-P3 oracle input (research/ts-p3.md 2): an ext4 copy of the real-track MS
# with RESIDUAL_DATA := RESIDUAL2_DATA (the tsp2-real2 injected residual) and
# WEIGHT_SPECTRUM := 1 in every cell (FLAG and FLAG_ROW unchanged), written by
# python-casacore inside rang-o-casa:6.7.6.14, no network. WSClean then images
# it with its default weights, which are the unit weights of
# `rang-core lightcurve --weights unit`.
#
#   bash unit_copy.sh SRC_MS EXT4_DIR
set -euo pipefail
src=$1; out=$(realpath -m "$2")
mkdir -p "$out"
name=$(basename "$src")
start=$(date +%s)
cp -r "$src" "$out/$name"
echo "copy_s $(( $(date +%s) - start ))" > "$out/unit-copy-time.txt"
cat > "$out/unit.py" <<'PY'
import sys, time
import numpy as np
from casacore.tables import table
t0 = time.time()
t = table(sys.argv[1], readonly=False, ack=False)
n = t.nrows()
step = 20000
for s in range(0, n, step):
    k = min(step, n - s)
    t.putcol("RESIDUAL_DATA", t.getcol("RESIDUAL2_DATA", s, k), s, k)
    ws = t.getcol("WEIGHT_SPECTRUM", s, k)
    t.putcol("WEIGHT_SPECTRUM", np.ones_like(ws), s, k)
t.close()
print("unit_s", time.time() - t0)
PY
docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp -e HOME=/tmp \
  -v "$out:$out" -w "$out" rang-o-casa:6.7.6.14 \
  python3 -I "$out/unit.py" "$out/$name" >> "$out/unit-copy-time.txt" 2>&1
cat "$out/unit-copy-time.txt"
