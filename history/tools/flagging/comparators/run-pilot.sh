#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../../.." && pwd)"
rang_run="${1:-outputs/tv-comparators-pilot}"
if (($#)); then shift; fi
mkdir -p "$rang_root/outputs/comparator-numba-cache" "$rang_root/outputs/tricolour-numba-cache"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e NUMBA_CACHE_DIR=/tmp/quartical-cache \
  -v "$rang_root:/workspace:ro" \
  -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/comparator-numba-cache:/tmp/quartical-cache:rw" \
  -v "$rang_root/outputs/tricolour-numba-cache:/tmp/tricolour-cache:rw" \
  rang-flagging-comparators:local -s opts.log.dir=outputs/stimela-comparator-logs \
  run /workspace/recipes/tv-flagging-comparators.yaml tv-flagging-comparators \
  archive=/workspace/outputs/ska-pointing/outer_scans.zip \
  "run-dir=/workspace/$rang_run" "$@"
