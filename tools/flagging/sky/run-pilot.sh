#!/usr/bin/env bash
set -euo pipefail

sky_run_dir="${1:-outputs/tv-flagging-sky-01}"
if [[ "$sky_run_dir" != outputs/* || "$sky_run_dir" == *..* ]]; then
  echo "Use a fresh relative directory underneath outputs/" >&2
  exit 2
fi
shift || true
mkdir -p outputs/flagging-sky-numba-cache
docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -v "$PWD:/workspace:ro" -v "$PWD/outputs:/workspace/outputs:rw" \
  -v "$PWD/outputs/flagging-sky-numba-cache:/tmp/numba" \
  rang-flagging-sky:local -s opts.log.dir=outputs/stimela-flagging-sky-logs \
  run recipes/tv-flagging-sky.yaml tv-flagging-sky \
  "run-dir=/workspace/$sky_run_dir" \
  archive=/workspace/outputs/ska-pointing/outer_scans.zip \
  sky-model=/workspace/outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt "$@"
