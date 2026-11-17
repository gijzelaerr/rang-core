#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Run a tfcrop probe job in CASA (research/v8-tfcrop.md; labelled probe).
# Usage: bash tools/oracles/casa/tfcrop_probe.sh SRC_DIR WSL_DIR JOB.json
# SRC_DIR (templates, designs, the job; usually under /mnt/d) is copied to
# WSL_DIR on ext4 (casacore bulk I/O over 9p hit ENOMEM before), CASA runs
# there with the job's paths relative to /p, and the outputs (WSL_DIR/out)
# are copied back to SRC_DIR/out.
set -euo pipefail
code=$(cd "$(dirname "$0")" && pwd)
src=$(realpath "$1")
dst=$(realpath -m "$2")
job=$3
image=${RANG_CASA_IMAGE:-rang-o-casa:6.7.6.14}
mkdir -p "$dst"
rsync -a --exclude out "$src/" "$dst/"
rm -rf "$dst/out"
mkdir -p "$dst/out"
docker image inspect "$image" --format '{{.Id}}' > "$dst/out/image.txt"
sha256sum "$code/tfcrop_probe_casa.py" > "$dst/out/code-sha256.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none \
  --tmpfs /tmp:size=8g -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$dst:/p" -v "$code:/code:ro" -w /p "$image" \
  /usr/bin/time -f "%e %M %x" -o /p/out/time.txt \
  /opt/casa/bin/python -I /code/tfcrop_probe_casa.py /p/out "/p/$job" > "$dst/out/log.txt" 2>&1 || true
rm -rf "$src/out"
cp -r "$dst/out" "$src/out"
tail -3 "$dst/out/log.txt"; cat "$dst/out/time.txt"
