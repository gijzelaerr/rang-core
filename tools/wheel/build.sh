#!/usr/bin/env bash
# Usage: bash tools/wheel/build.sh OUT_DIR [x86_64|aarch64]
#
# Builds the distributable rangtoy wheel (abi3-py310, manylinux_2_28) and the
# sdist inside the pinned manylinux container (research/wheel.md). The
# checkout is mounted read-only at its own path, so nothing is written into
# the tree; the cargo target directory lives in OUT_DIR/target and is removed
# afterwards unless KEEP_TARGET=1. Rustup and the cargo registry are cached
# under ~/Build/cache (safe to wipe). Writes OUT_DIR/dist/*.whl, *.tar.gz,
# auditwheel-show.txt, unzip-l.txt, sdist-list.txt and build.log, and the
# wall time of every step into OUT_DIR/timings.tsv. Needs docker.
#
# aarch64 cross-builds with zig in the same x86_64 container
# (maturin --zig); auditwheel cannot run there for a foreign architecture,
# so maturin's own manylinux check is the only policy check of that wheel.
set -euo pipefail
cd "$(dirname "$0")/../.."
src=$(pwd -P)
out=$1
arch=${2:-x86_64}
[ -e "$out" ] && { echo "$out exists"; exit 2; }
mkdir -p "$out/dist"
out=$(cd "$out" && pwd -P)

IMAGE=${WHEEL_IMAGE:-quay.io/pypa/manylinux_2_28_x86_64@sha256:e0adf18521ad35192df733a6c62d35df7801957d24e0470238aacecfab2188a3}
export RUST_VERSION=${RUST_VERSION:-1.93.1}
export MATURIN_VERSION=${MATURIN_VERSION:-1.16.0}
export ZIG_VERSION=${ZIG_VERSION:-0.13.0}
cache=${WHEEL_CACHE:-$HOME/Build/cache/rang-wheel}
mkdir -p "$cache/rustup" "$cache/cargo" "$cache/pip"

# A worktree's .git is a file naming the main repository's git directory;
# mount that read-only too, so maturin's sdist can ask git for the file list.
mounts=(-v "$src:$src:ro" -v "$out:$out")
if [ -f .git ]; then
  common=$(git rev-parse --git-common-dir)
  common=$(cd "$common" && pwd -P)
  mounts+=(-v "$common:$common:ro")
fi

echo "image $IMAGE rust $RUST_VERSION maturin $MATURIN_VERSION arch $arch"
git rev-parse HEAD > "$out/source-commit.txt"
git status --short > "$out/source-status.txt"
start=$(date +%s.%N)
docker run --rm --user "$(id -u):$(id -g)" \
  "${mounts[@]}" \
  -v "$cache/rustup:/cache/rustup" -v "$cache/cargo:/cache/cargo" -v "$cache/pip:/cache/pip" \
  -e HOME=/tmp -e RUSTUP_HOME=/cache/rustup -e CARGO_HOME=/cache/cargo \
  -e PIP_CACHE_DIR=/cache/pip -e CARGO_TARGET_DIR="$out/target" \
  -e RUST_VERSION -e MATURIN_VERSION -e ZIG_VERSION -e ARCH="$arch" \
  -e SRC="$src" -e OUT="$out" -w "$src" \
  "$IMAGE" bash "$src/tools/wheel/build-inside.sh" 2>&1 | tee "$out/build.log"
end=$(date +%s.%N)
printf 'container total\t%.1f\n' "$(python3 -c "print($end - $start)")" >> "$out/timings.tsv"
[ "${KEEP_TARGET:-0}" = 1 ] || rm -rf "$out/target"
cd "$out/dist" && sha256sum ./* | tee "$out/sha256.txt"
ls -l "$out/dist"
cat "$out/timings.tsv"
