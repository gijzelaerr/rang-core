#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# TS-P2 real track (research/ts-p2.md 4.2, step 5): CASA 6.7.6.14 split of
# the replayed E2-A MS, field ESO137-001, datacolumn corrected, width 8
# (512 channels, as E2-A's image.average_channels: 8). Runs on the WSL host
# inside rang-o-casa:6.7.6.14, no network; reads the replay over 9p, writes
# the split on ext4, then copies it back beside the replay.
#
#   bash split_scan10.sh /mnt/d/rang/outputs/p1-lightcurves-20261123 EXT4_DIR
set -euo pipefail
root=$1; ext=$(realpath -m "$2")
mkdir -p "$ext"
cat > "$ext/split.py" <<'PY'
import time
from casatasks import split
t = time.time()
split(vis="/in/e2a-replay.ms", outputvis="/out/scan10-512.ms", field="ESO137-001",
      datacolumn="corrected", width=8, keepflags=True)
print("split_s", time.time() - t)
PY
docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp -e HOME=/tmp \
  -e OMP_NUM_THREADS=4 -v "$root:/in:ro" -v "$ext:/out" -w /out rang-o-casa:6.7.6.14 \
  /usr/bin/time -f "%e %M %x" -o /out/split-time.txt \
  /opt/casa/bin/python -I /out/split.py > "$ext/split.log" 2>&1
cat "$ext/split-time.txt"
start=$(date +%s)
cp -r "$ext/scan10-512.ms" "$root/scan10-512.ms"
echo "copy_back_s $(( $(date +%s) - start ))" >> "$ext/split-time.txt"
