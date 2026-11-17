#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the E6 C++ casacore oracle image (research/e6-table-writer-final.md) and
# record its id, size, build time and the installed deb versions.
# Usage: bash tools/oracles/casacore-cpp/build.sh [tag] [record.json]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tag=${1:-rang-casacore-cpp:3.7.1}
record=${2:-}
start=$(date +%s.%N)
docker build --pull=false -t "$tag" "$here"
end=$(date +%s.%N)
id=$(docker image inspect "$tag" --format '{{.Id}}')
size=$(docker image inspect "$tag" --format '{{.Size}}')
wall=$(python3 -c "print(round($end - $start, 1))")
echo "image $tag id $id size $size bytes build ${wall} s"
if [ -n "$record" ]; then
  docker run --rm --network none --entrypoint cat "$tag" /opt/image-debs.txt > "${record%.json}-debs.txt"
  python3 - "$record" "$tag" "$id" "$size" "$wall" "${record%.json}-debs.txt" <<'PY'
import datetime, json, sys
record, tag, image_id, size, wall, debs_path = sys.argv[1:]
debs = dict(line.strip().split("=", 1) for line in open(debs_path) if "=" in line)
keep = ("casacore-dev", "g++", "libhdf5-103-1t64")
json.dump({
    "tag": tag,
    "id": image_id,
    "size_bytes": int(size),
    "build_seconds": float(wall),
    "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "base": "ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852",
    "ppa": "ppa:kernsuite/kern-10",
    "debs": {k: v for k, v in sorted(debs.items())
             if k.split(":")[0] in keep or k.startswith(("libcasa-", "libhdf5", "g++"))},
    "deb_count": len(debs),
}, open(record, "w"), indent=1)
PY
fi
