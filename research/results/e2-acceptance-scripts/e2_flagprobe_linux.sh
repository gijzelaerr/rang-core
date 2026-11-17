#!/usr/bin/env bash
# E2 flag probe: a Linux build of the rang core from this worktree, and the
# probe runs with it. From WSL:
#   bash e2_flagprobe_linux.sh OUT
# Builds a release wheel (maturin, CARGO_TARGET_DIR=OUT/linux-target) under
# tools/heavy_lock.py, installs it into the uv venv OUT/linux-venv and runs
# e2_flagprobe_rang.py on OUT/group-scan1.npz (baseline and all), logging
# START/END lines with wall seconds to OUT/linux.log.
set -eu
out=$1
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
log=$out/linux.log
export PATH=$HOME/.cargo/bin:$HOME/.local/bin:$PATH
export CARGO_TARGET_DIR=$out/linux-target
export UV_CACHE_DIR=$out/linux-uv-cache
venv=$out/linux-venv
[ -d "$venv" ] || uv venv --python 3.12 "$venv"
uv pip install --python "$venv/bin/python" --index-url https://pypi.org/simple \
  "maturin>=1.16,<2" numpy pyyaml
s=$(date +%s.%N)
echo "START $(date -Is) build" >>"$log"
cd "$root"
python3 tools/heavy_lock.py run -- "$venv/bin/maturin" build --release \
  --out "$out/linux-wheel" >>"$log" 2>&1
echo "END $(date -Is) build wall $(echo "$(date +%s.%N) - $s" | bc) s" >>"$log"
uv pip install --python "$venv/bin/python" --reinstall --no-deps \
  "$out"/linux-wheel/rang_core-*.whl
for m in baseline all; do
  s=$(date +%s.%N)
  cd "$out"
  python3 "$root/tools/heavy_lock.py" run -- "$venv/bin/python" \
    "$here/e2_flagprobe_rang.py" "$out/group-scan1.npz" "$out/strategy.yaml" \
    "$out/rang-linux-$m.npz" "$m" >>"$log" 2>&1
  echo "END $(date -Is) rang-linux-$m wall $(echo "$(date +%s.%N) - $s" | bc) s" >>"$log"
done
