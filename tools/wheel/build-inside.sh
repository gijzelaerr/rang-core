#!/usr/bin/env bash
# Runs inside the manylinux_2_28 container; called by tools/wheel/build.sh,
# which sets SRC, OUT, ARCH, RUST_VERSION, MATURIN_VERSION, ZIG_VERSION,
# RUSTUP_HOME, CARGO_HOME and CARGO_TARGET_DIR.
set -euo pipefail
cd "$SRC"
timings=$OUT/timings.tsv
t() {
  local name=$1; shift
  local s e
  s=$(date +%s.%N)
  "$@"
  e=$(date +%s.%N)
  printf '%s\t%.1f\n' "$name" "$(/opt/python/cp312-cp312/bin/python -c "print($e - $s)")" >> "$timings"
}

install_rust() {
  if [ ! -x "$CARGO_HOME/bin/rustup" ]; then
    curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal \
      --default-toolchain none
  fi
  "$CARGO_HOME/bin/rustup" toolchain install "$RUST_VERSION" --profile minimal
  if [ "$ARCH" = aarch64 ]; then
    "$CARGO_HOME/bin/rustup" target add --toolchain "$RUST_VERSION" aarch64-unknown-linux-gnu
  fi
}
t rustup install_rust
export PATH=$CARGO_HOME/bin:$PATH
export RUSTUP_TOOLCHAIN=$RUST_VERSION
# Distributable binaries use the baseline ISA of each target. The checkout's
# .cargo/config.toml may set target-cpu=x86-64-v3 for local builds; an
# environment RUSTFLAGS overrides every config-file rustflags.
if [ "$ARCH" = aarch64 ]; then
  export RUSTFLAGS="-C target-cpu=generic"
else
  export RUSTFLAGS="-C target-cpu=x86-64"
fi
echo "RUSTFLAGS=$RUSTFLAGS"

tools=/tmp/tools
make_tools() {
  /opt/python/cp312-cp312/bin/python -m venv "$tools"
  local extra=()
  [ "$ARCH" = aarch64 ] && extra=("ziglang==$ZIG_VERSION")
  "$tools/bin/pip" install -q --index-url https://pypi.org/simple \
    "maturin==$MATURIN_VERSION" "${extra[@]}"
}
t tools make_tools
# maturin --zig runs `python3 -m ziglang`; the tools venv has it.
export PATH=$tools/bin:$PATH
rustc -V
cargo -V
"$tools/bin/maturin" --version

dist=$OUT/dist
if [ "$ARCH" = aarch64 ]; then
  t wheel "$tools/bin/maturin" build --release --locked --zig \
    --target aarch64-unknown-linux-gnu --manylinux 2_28 --out "$dist"
  exit 0
fi

# abi3: one interpreter is enough; maturin tags cp310-abi3 and checks the
# manylinux_2_28 policy itself (its built-in auditwheel).
t wheel "$tools/bin/maturin" build --release --locked --manylinux 2_28 \
  -i /opt/python/cp310-cp310/bin/python --out "$dist"
t sdist "$tools/bin/maturin" sdist --out "$dist"

whl=$(ls "$dist"/*.whl)
auditwheel show "$whl" | tee "$OUT/auditwheel-show.txt"
# Repair is a no-op when the wheel needs no external library; run it into a
# separate directory and keep the original if the repaired one is identical.
t repair auditwheel repair --plat manylinux_2_28_x86_64 -w "$OUT/repaired" "$whl" \
  > "$OUT/auditwheel-repair.txt" 2>&1 || true
cat "$OUT/auditwheel-repair.txt"
/opt/python/cp312-cp312/bin/python -m zipfile -l "$whl" | tee "$OUT/unzip-l.txt"
/opt/python/cp312-cp312/bin/python -m zipfile -e "$whl" /tmp/wheel-unzip
sha256sum /tmp/wheel-unzip/rangtoy/_core.abi3.so | tee "$OUT/core-sha256.txt"
tar tzvf "$dist"/*.tar.gz > "$OUT/sdist-list.txt"
wc -l < "$OUT/sdist-list.txt"

# No C ABI library is built beside the wheel any more: the backend tests
# compare the wheel with an archive, and the root crate's kernels are in the
# extension (task P7, research/p7-architecture.md).

# The sdist must build on its own (the path CI and pip take without a wheel).
sdist_build() {
  rm -rf /tmp/sdist && mkdir -p /tmp/sdist
  tar xzf "$dist"/*.tar.gz -C /tmp/sdist
  # From the unpacked sdist's own pyproject.toml (manifest-path core/py).
  (cd /tmp/sdist/rangtoy-* && CARGO_TARGET_DIR=/tmp/sdist-target "$tools/bin/maturin" \
    build --release --locked --manylinux 2_28 -i /opt/python/cp310-cp310/bin/python \
    --out "$OUT/from-sdist")
  /opt/python/cp312-cp312/bin/python -m zipfile -e "$OUT"/from-sdist/*.whl /tmp/sdist-unzip
  sha256sum /tmp/sdist-unzip/rangtoy/_core.abi3.so | tee "$OUT/from-sdist/core-sha256.txt"
}
t sdist-wheel sdist_build
