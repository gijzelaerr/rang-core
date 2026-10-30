#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-influence.sh outputs/fresh-influence outputs/completed-suite [--dry-run]}"
rang_source="${2:?Supply completed balanced suite}"
shift 2
for rang_assignment in "$@"; do
  case "$rang_assignment" in --dry-run) ;; *) echo "Only --dry-run is accepted; scientific settings are frozen" >&2; exit 2 ;; esac
done
for rang_path in "$rang_run" "$rang_source"; do
  case "$rang_path" in outputs/*) ;; *) echo "Paths must be relative beneath outputs/" >&2; exit 2 ;; esac
  case "/$rang_path/" in */../*|*/./*) echo "No traversal components allowed" >&2; exit 2 ;; esac
done
python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_source"
mkdir -p "$(dirname "$rang_root/$rang_run-logs")"
mkdir "$rang_root/$rang_run-logs"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-response:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-influence.yaml tv-flagging-influence \
  "run-dir=/workspace/$rang_run" "source-dir=/workspace/$rang_source" "$@"
