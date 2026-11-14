#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# V8b's held-out ESO137 subset (research/v8b-flagdata.md, amendment 1):
# CASA split of the first 600 s of scan 2 of the ESO137 pilot raw MS, all
# 512 channels, flags kept, DATA only, into $out/eso137-ho.ms.
# Usage: bash tools/oracles/casa/v8b_heldout.sh [OUT_DIR]
set -euo pipefail
out=$(realpath -m "${1:-/mnt/d/rang/scratch/v8b-20261113/heldout}")
raw=/mnt/d/rang/outputs/20261103-gemclean-heldout/real/raw.ms
image=${RANG_CASA_IMAGE:-rang-o-casa:6.7.6.14}
if [ -e "$out/eso137-ho.ms" ]; then echo "$out/eso137-ho.ms exists" >&2; exit 1; fi
mkdir -p "$out"
docker run --rm --user "$(id -u):$(id -g)" --network none \
  --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$raw:/in/raw.ms:ro" -v "$out:/out" -w /tmp "$image" \
  /usr/bin/time -f "%e %M %x" -o /out/split-time.txt \
  /opt/casa/bin/python -I -c "
from casatasks import split
split(vis='/in/raw.ms', outputvis='/out/eso137-ho.ms', scan='2',
      timerange='2019/05/09/20:39:49.483~20:49:49.483', keepflags=True,
      datacolumn='data')
" > "$out/split-log.txt" 2>&1
docker image inspect "$image" --format '{{.Id}}' > "$out/split-image.txt"
