#!/usr/bin/env bash
# Build the DF5-O pfb-imaging oracle image and record its id, size and time.
# Usage: bash tools/oracles/pfb-imaging/build.sh [tag] [record.json]
# The lock was resolved on the host (uv 0.12.23, 2026-10-31):
#   uv pip compile requirements.in --python-version 3.12 \
#     --python-platform x86_64-manylinux_2_39 --generate-hashes \
#     --index-url https://pypi.org/simple --no-header -o requirements.lock
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tag=${1:-rang-pfb-imaging:0.0.11}
record=${2:-}
start=$(date +%s.%N)
docker build --pull=false -t "$tag" "$here"
end=$(date +%s.%N)
id=$(docker image inspect "$tag" --format '{{.Id}}')
size=$(docker image inspect "$tag" --format '{{.Size}}')
wall=$(python3 -c "print(round($end - $start, 1))")
pfb=$(docker run --rm --network none "$tag" python -c "import importlib.metadata as m; print(m.version('pfb-imaging'), m.version('ducc0'), m.version('python-casacore'), m.version('dask-ms'), m.version('codex-africanus'))")
echo "image $tag id $id size $size bytes build ${wall} s versions $pfb"
if [ -n "$record" ]; then
  printf '{"tag": "%s", "id": "%s", "size_bytes": %s, "build_seconds": %s, "versions": "%s", "date": "%s"}\n' \
    "$tag" "$id" "$size" "$wall" "$pfb" "$(date -u +%FT%TZ)" > "$record"
fi
