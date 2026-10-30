#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-next.sh outputs/fresh outputs/prepared outputs/historical outputs/response outputs/provenance outputs/caracal [--dry-run]}"
rang_prepared="${2:?Supply stable clean prepared input}"
rang_historical="${3:?Supply stable historical gain suite}"
rang_response="${4:?Supply stable signed response controls}"
rang_provenance="${5:?Supply complete separately acquired metadata}"
rang_caracal="${6:?Supply stable full-strategy CARACAL controls}"
shift 6
for rang_option in "$@"; do
  case "$rang_option" in --dry-run) ;; *) echo "Only --dry-run is accepted; settings are frozen" >&2; exit 2 ;; esac
done
for rang_path in "$rang_run" "$rang_prepared" "$rang_historical" "$rang_response" "$rang_provenance" "$rang_caracal"; do
  case "$rang_path" in outputs/*) ;; *) echo "Paths must be relative beneath outputs/" >&2; exit 2 ;; esac
  case "/$rang_path/" in */../*|*/./*) echo "No traversal components allowed" >&2; exit 2 ;; esac
done
python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_prepared" "$rang_historical" "$rang_response" "$rang_provenance" "$rang_caracal"
mkdir -p "$(dirname "$rang_root/$rang_run-logs")"
mkdir "$rang_root/$rang_run-logs"
mkdir -p "$rang_root/outputs/flagging-next-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-next-imaging:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" -e NUMBA_CACHE_DIR=/tmp/numba \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/$rang_prepared:/workspace/$rang_prepared:ro" \
  -v "$rang_root/$rang_historical:/workspace/$rang_historical:ro" \
  -v "$rang_root/$rang_response:/workspace/$rang_response:ro" \
  -v "$rang_root/$rang_provenance:/workspace/$rang_provenance:ro" \
  -v "$rang_root/$rang_caracal:/workspace/$rang_caracal:ro" \
  -v "$rang_root/outputs/flagging-next-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-next.yaml tv-flagging-next \
  "run-dir=/workspace/$rang_run" "prepared-dir=/workspace/$rang_prepared" \
  "historical-dir=/workspace/$rang_historical" "response-dir=/workspace/$rang_response" \
  "provenance-dir=/workspace/$rang_provenance" "caracal-dir=/workspace/$rang_caracal" "$@"
