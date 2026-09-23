#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:-outputs/tv-flagging-pilot}"
if (($#)); then shift; fi
mkdir -p "$rang_root/outputs/flagging-numba-cache"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -v "$rang_root:/workspace:ro" \
  -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-numba-cache:/tmp/numba:rw" \
  rang-flagging:local -s opts.log.dir=outputs/stimela-flagging-logs \
  run /workspace/recipes/tv-flagging.yaml tv-flagging \
  archive=/workspace/outputs/ska-pointing/outer_scans.zip \
  "run-dir=/workspace/$rang_run" "$@"
