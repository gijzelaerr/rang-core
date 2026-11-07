#!/usr/bin/env bash
# The venv for CARACal's get_refant reference run (task E0,
# research/e0-refant-extend.md section 3.1): msutils 1.2.0 (the last 1.x, what
# Stimela's unpinned `pip install msutils` base image held), Python 3.11
# (msutils imports distutils), numpy < 2 (msutils calls numpy.product), and
# casacore's measures data copied from the O-CASA image.
# Usage: bash tools/oracles/e0/msutils-venv.sh <dir> <msutils-1.2.0.tar.gz>
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
dir=$(realpath -m "$1")
sdist=$(realpath "$2")
echo "a377d8b55ef285341fd65565ae9081d22ec452da2e2d7c6ce4eda0ba74be17af  $sdist" | sha256sum -c
mkdir -p "$dir/home"
uv venv --clear "$dir/venv" --python 3.11
uv pip install --python "$dir/venv/bin/python" --index-url https://pypi.org/simple \
  "numpy<2" python-casacore dask-ms "dask[array]<2024.8" bokeh setuptools
uv pip install --python "$dir/venv/bin/python" --index-url https://pypi.org/simple --no-deps "$sdist"
if [ ! -f "$dir/casacore-data/geodetic/Observatories/table.dat" ]; then
  rm -rf "$dir/casacore-data"
  mkdir -p "$dir/casacore-data"
  # tar -h: the image's data directory holds symbolic links into the package.
  # Dangling links in the *.old tables are skipped (tar exits 1 on them).
  docker run --rm --network none rang-o-casa:6.7.6.14 \
    tar -chf - -C /usr/share/casacore/data . | tar -xf - -C "$dir/casacore-data" || true
  test -f "$dir/casacore-data/geodetic/Observatories/table.dat"
fi
echo "measures.directory: $dir/casacore-data" > "$dir/home/.casarc"
uv pip freeze --python "$dir/venv/bin/python" > "$dir/freeze.txt"
HOME="$dir/home" "$dir/venv/bin/python" -c "
import casacore.measures as m
print(m.measures().observatory('MeerKAT'))
import MSUtils.flag_stats
print('msutils ok')
"
