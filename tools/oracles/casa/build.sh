#!/usr/bin/env bash
# Build the O-CASA oracle image (research/o-casa.md) and record time and size.
# Usage: bash tools/oracles/casa/build.sh [tag] [record.json]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tag=${1:-rang-o-casa:6.7.6.14}
record=${2:-}
start=$(date +%s.%N)
docker build --pull=false -t "$tag" "$here"
end=$(date +%s.%N)
id=$(docker image inspect "$tag" --format '{{.Id}}')
size=$(docker image inspect "$tag" --format '{{.Size}}')
wall=$(python3 -c "print(round($end - $start, 1))")
echo "image $tag id $id size $size bytes build ${wall} s"
if [ -n "$record" ]; then
  printf '{"tag": "%s", "id": "%s", "size_bytes": %s, "build_seconds": %s, "date": "%s"}\n' \
    "$tag" "$id" "$size" "$wall" "$(date -u +%FT%TZ)" > "$record"
fi
