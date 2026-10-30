#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-response.sh outputs/fresh-response outputs/prepared-clean [--dry-run]}"
rang_prepared="${2:?Supply stable clean prepared input}"
shift 2
for rang_assignment in "$@"; do
  case "$rang_assignment" in --dry-run) ;; *) echo "Only --dry-run is accepted; scientific settings are frozen" >&2; exit 2 ;; esac
done
for rang_path in "$rang_run" "$rang_prepared"; do
  case "$rang_path" in outputs/*) ;; *) echo "Paths must be relative beneath outputs/" >&2; exit 2 ;; esac
  case "/$rang_path/" in */../*|*/./*) echo "No traversal components allowed" >&2; exit 2 ;; esac
done
python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_prepared"
mkdir -p "$(dirname "$rang_root/$rang_run-logs")"
mkdir "$rang_root/$rang_run-logs"
mkdir -p "$rang_root/outputs/flagging-response-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-response:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" -e NUMBA_CACHE_DIR=/tmp/numba \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-response-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-response.yaml tv-flagging-response \
  "run-dir=/workspace/$rang_run" "prepared-dir=/workspace/$rang_prepared" "$@"
