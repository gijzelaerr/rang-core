#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-caracal.sh outputs/fresh-run outputs/prepared-input [recipe assignments]}"
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
python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_prepared" \
  outputs/caracal-strategy-inputs-8f7bb363
mkdir -p "$(dirname "$rang_root/$rang_run-logs")"
mkdir "$rang_root/$rang_run-logs"
mkdir -p "$rang_root/outputs/flagging-caracal-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-parallel:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" \
  -e NUMBA_CACHE_DIR=/tmp/numba/base -e RANG_TRICOLOUR_CACHE_DIR=/tmp/numba/tricolour \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-caracal-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-caracal.yaml tv-flagging-caracal \
  "run-dir=/workspace/$rang_run" "prepared-dir=/workspace/$rang_prepared" \
  strategy-dir=/workspace/outputs/caracal-strategy-inputs-8f7bb363 "$@"
