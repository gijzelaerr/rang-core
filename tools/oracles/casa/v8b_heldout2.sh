#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# V8b's second held-out split (research/v8b-flagdata.md, amendment 3): CASA
# split of scan 19 of the E2-B LUNO calibrators MS, all channels, flags kept,
# DATA only, into $out/luno-ho2.ms.
# Usage: bash tools/oracles/casa/v8b_heldout2.sh [OUT_DIR]
set -euo pipefail
out=$(realpath -m "${1:-/mnt/d/rang/scratch/v8b-20261113/heldout}")
raw=/mnt/d/rang/data/e2-b/e2b.ms
image=${RANG_CASA_IMAGE:-rang-o-casa:6.7.6.14}
if [ -e "$out/luno-ho2.ms" ]; then echo "$out/luno-ho2.ms exists" >&2; exit 1; fi
mkdir -p "$out"
docker run --rm --user "$(id -u):$(id -g)" --network none \
  --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$raw:/in/raw.ms:ro" -v "$out:/out" -w /tmp "$image" \
  /usr/bin/time -f "%e %M %x" -o /out/split2-time.txt \
  /opt/casa/bin/python -I -c "
from casatasks import split
split(vis='/in/raw.ms', outputvis='/out/luno-ho2.ms', scan='19',
      keepflags=True, datacolumn='data')
" > "$out/split2-log.txt" 2>&1
docker image inspect "$image" --format '{{.Id}}' > "$out/split2-image.txt"
