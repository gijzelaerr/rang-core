#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-structured.sh outputs/fresh-run outputs/prepared-input [recipe assignments]}"
rang_prepared="${2:?Supply an existing stable prepared input}"
shift 2
for rang_path in "$rang_run" "$rang_prepared"; do
  case "$rang_path" in outputs/*) ;; *) echo "Paths must be relative beneath outputs/" >&2; exit 2 ;; esac
  case "/$rang_path/" in */../*|*/./*) echo "No traversal components allowed" >&2; exit 2 ;; esac
done
if [[ -e "$rang_root/$rang_run" ]]; then
  echo "Choose a fresh output directory" >&2
  exit 2
fi
mkdir -p "$rang_root/outputs/flagging-structured-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-parallel:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" -e NUMBA_CACHE_DIR=/tmp/numba \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-structured-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-structured.yaml tv-flagging-structured \
  "run-dir=/workspace/$rang_run" "prepared-dir=/workspace/$rang_prepared" "$@"
