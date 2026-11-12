#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# CASA listobs on the V8a MSs, read-only (research/v8a-listobs.md).
# Usage: bash tools/oracles/casa/listobs.sh OUT_DIR [image]
# MSs: the LUNO 1934-638 slice (outputs/luno-solve-20261029-02/work.ms) and
# the five public fixture MSs (outer_scans.zip, extracted by rang.notebook);
# A1's simulated MS as C2a's CASA run left it (16 antennas, 4 fields, 20+
# scans); the ESO137 pilot raw MS (61 antennas, metadata only).
set -euo pipefail
code=$(cd "$(dirname "$0")" && pwd)
run=$(realpath -m "$1")
image=${2:-rang-o-casa:6.7.6.14}
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run"
luno=$(realpath "$HOME/Github/rang/outputs/luno-solve-20261029-02/work.ms")
fixture=$(realpath "$HOME/.cache/rang-notebook/fixture-scan9/outer_scans")
args=(luno=/ms/luno.ms)
a1=/mnt/d/rang/outputs/c2a-20261106-03/casa/a1.ms
eso=/mnt/d/rang/outputs/20261103-gemclean-heldout/real/raw.ms
args+=(a1=/ms/a1.ms eso137=/ms/eso137.ms)
for s in 1 4 5 8 9; do args+=("fixture-scan$s=/ms/fixture/1672727931_sdp_l0_scan_$s.ms"); done
date -u +%FT%TZ > "$run/started.txt"
docker image inspect "$image" --format '{{.Id}}' > "$run/image.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none \
  --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$luno:/ms/luno.ms:ro" -v "$fixture:/ms/fixture:ro"   -v "$a1:/ms/a1.ms:ro" -v "$eso:/ms/eso137.ms:ro" -v "$code:/code:ro" \
  -v "$run:/run" -w /tmp "$image" \
  /usr/bin/time -f "%e %M %x" -o /run/time.txt \
  /opt/casa/bin/python -I /code/listobs.py /run "${args[@]}" > "$run/log.txt" 2>&1
sha256sum "$code/listobs.py" "$code/listobs.sh" > "$run/code-sha256.txt"
date -u +%FT%TZ > "$run/finished.txt"
