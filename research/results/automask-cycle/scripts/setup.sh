#!/bin/bash
# setup.sh WORKTREE: venv, SciPy/Astropy (sdm03 amendment 2), extension release build
set -e
source ~/.rang-env.sh
W=$1; cd $W
uv venv -q --python 3.14 .venv
for m in Cargo.toml core/Cargo.toml core/py/Cargo.toml; do cargo +1.93 fetch -q --manifest-path $m; done
VIRTUAL_ENV=$W/.venv uv pip install -q -e ".[test]" maturin scipy==1.18.1 astropy==8.0.3 2>&1 | tail -2
cd core/py && VIRTUAL_ENV=$W/.venv CARGO_BUILD_JOBS=8 $W/.venv/bin/maturin develop --release -q 2>&1 | tail -3
cd $W && .venv/bin/python -c "import rang, rang.core as c; print(c.library_path())"
sha256sum $W/python/rang/_core.abi3.so
echo SETUP-DONE
