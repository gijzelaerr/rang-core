#!/bin/bash
set -e
source ~/.rang-env.sh
cd ~/Worktrees/rang/sdm03-default
uv venv -q --python 3.14 .venv
for m in Cargo.toml core/Cargo.toml core/py/Cargo.toml; do cargo +1.93 fetch -q --manifest-path $m; done
VIRTUAL_ENV=$PWD/.venv uv pip install -q -e ".[test]" maturin 2>&1 | tail -2
cd core/py && VIRTUAL_ENV=$HOME/Worktrees/rang/sdm03-default/.venv CARGO_BUILD_JOBS=8 $HOME/Worktrees/rang/sdm03-default/.venv/bin/maturin develop --release -q 2>&1 | tail -3
cd ~/Worktrees/rang/sdm03-default && .venv/bin/python -c "import rang, rang.core as c; print(c.library_path())"
echo SETUP-DONE
