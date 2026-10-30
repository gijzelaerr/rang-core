#!/usr/bin/env bash
# Run examples/solve_luno.py in the pinned image with a persistent Numba cache.
# The cache lives in outputs/numba-cache/<image id>, so a rebuilt image starts
# cold instead of reusing code compiled against other library versions. With a
# warm cache a small solve takes about 3 s instead of about 29 s
# (research/upstream-notes.md). Frozen campaign scripts are unchanged.
set -euo pipefail
cd "$(dirname "$0")/../.."
ms="${1:?Usage: bash tools/flagging/run-luno-solve.sh outputs/<run>/work.ms outputs/<run>/solve}"
out="${2:?Usage: bash tools/flagging/run-luno-solve.sh outputs/<run>/work.ms outputs/<run>/solve}"
image="${RANG_FLAGGING_IMAGE:-rang-flagging:local}"
for path in "$ms" "$out"; do
  case "$path" in outputs/*) ;; *) echo "Paths must be beneath outputs/" >&2; exit 2 ;; esac
done
test -d "$ms"
test ! -e "$out"
run=$(dirname "$ms")
test "$(dirname "$out")" = "$run" || { echo "MS and output must share a run directory" >&2; exit 2; }
id=$(docker image inspect --format '{{.Id}}' "$image" | sed 's/^sha256://' | cut -c1-16)
cache="outputs/numba-cache/$id"
mkdir -p "$cache"
docker run --rm --user "$(id -u):$(id -g)" --platform linux/amd64 --network none \
  --tmpfs /tmp -e HOME=/tmp -e NUMBA_CACHE_DIR=/numba \
  -v "$PWD/$cache:/numba" -v "$PWD/$run:/run" \
  -v "$PWD/examples/solve_luno.py:/solve_luno.py:ro" \
  --entrypoint python "$image" -I /solve_luno.py "/run/$(basename "$ms")" "/run/$(basename "$out")"
