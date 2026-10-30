#!/usr/bin/env bash
set -euo pipefail
rang_root="$(cd "$(dirname "$0")/../.." && pwd)"
rang_run="${1:?Usage: bash tools/flagging/run-signal.sh outputs/fresh-run outputs/prepared-input [recipe assignments]}"
rang_prepared="${2:?Supply an existing stable prepared input}"
shift 2
for rang_path in "$rang_run" "$rang_prepared"; do
  case "$rang_path" in outputs/*) ;; *) echo "Paths must be relative beneath outputs/" >&2; exit 2 ;; esac
  case "/$rang_path/" in */../*|*/./*) echo "No traversal components allowed" >&2; exit 2 ;; esac
done
rang_native=false
for rang_assignment in "$@"; do
  case "$rang_assignment" in
    run-dir=*|prepared-dir=*|mild-strategy=*)
      echo "Namespace assignments are fixed by this wrapper; use recipe directly for custom sources" >&2
      exit 2 ;;
    include-native=true) rang_native=true ;;
    include-native=false) rang_native=false ;;
  esac
done
rang_native_args=(include-native=false)
if [[ "$rang_native" == true ]]; then
  python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_prepared" outputs/caracal-strategy-inputs-8f7bb363
  if [[ ! -f "$rang_root/outputs/caracal-strategy-inputs-8f7bb363/calibrator_mild_flagging.yaml" ]]; then
    echo "Pinned CARACAL mild strategy is missing" >&2
    exit 2
  fi
  rang_native_args=(include-native=true mild-strategy=/workspace/outputs/caracal-strategy-inputs-8f7bb363/calibrator_mild_flagging.yaml)
else
  python3 "$rang_root/tools/flagging/preflight.py" "$rang_root" "$rang_run" "$rang_prepared"
fi
mkdir -p "$(dirname "$rang_root/$rang_run-logs")"
mkdir "$rang_root/$rang_run-logs"
mkdir -p "$rang_root/outputs/flagging-signal-numba-cache"
rang_image="$(docker image inspect --format '{{.Id}}' rang-flagging-parallel:local)"
exec docker run --rm --platform linux/amd64 --network none --read-only \
  --tmpfs /tmp --tmpfs /root/.stimela --tmpfs /root/.cache \
  -e "RANG_FLAGGING_SUITE_IMAGE=$rang_image" \
  -e NUMBA_CACHE_DIR=/tmp/numba/base -e RANG_TRICOLOUR_CACHE_DIR=/tmp/numba/tricolour \
  -v "$rang_root:/workspace:ro" -v "$rang_root/outputs:/workspace/outputs:rw" \
  -v "$rang_root/outputs/flagging-signal-numba-cache:/tmp/numba:rw" \
  "$rang_image" -s "opts.log.dir=$rang_run-logs" \
  run /workspace/recipes/tv-flagging-signal.yaml tv-flagging-signal \
  "run-dir=/workspace/$rang_run" "prepared-dir=/workspace/$rang_prepared" "${rang_native_args[@]}" "$@"
