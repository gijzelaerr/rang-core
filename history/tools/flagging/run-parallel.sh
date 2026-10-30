#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-parallel.sh outputs/fresh-run outputs/path/to/L-band-model.txt [recipe assignments]}"
rang_sky="${2:?Supply the pinned SARAO L-band calibrator catalog}"
shift 2
case "$rang_run" in
  outputs/*) ;;
  *) echo "Run directory must be a relative path beneath outputs/" >&2; exit 2 ;;
esac
case "/$rang_run/" in
  */../*|*/./*) echo "Run directory must not contain traversal components" >&2; exit 2 ;;
esac
if [[ -e "$rang_root/$rang_run" ]]; then
  echo "Run directory already exists; choose a fresh path" >&2
  exit 2
fi
if [[ ! -f "$rang_root/$rang_sky" ]]; then
  echo "Sky model must be an existing file relative to the checkout" >&2
  exit 2
fi
mkdir -p "$rang_root/outputs/flagging-parallel-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-parallel:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" \
  -v "$rang_root:/workspace:ro" \
  -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-parallel-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-parallel.yaml tv-flagging-parallel \
  archive=/workspace/outputs/ska-pointing/outer_scans.zip \
  "sky-model=/workspace/$rang_sky" "run-dir=/workspace/$rang_run" "$@"
