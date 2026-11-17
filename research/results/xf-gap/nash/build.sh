#!/bin/bash
# SPDX-License-Identifier: MIT
set -e
cd ~/Worktrees/rang/xf-gap
date -Is
uv venv -q --python 3.14 .venv
uv pip install -q --python .venv/bin/python maturin numpy pytest pyyaml scipy
. .venv/bin/activate
T0=$(date +%s)
CARGO_BUILD_JOBS=4 maturin develop --release -m core/py/Cargo.toml 2>&1 | tail -3
echo "maturin $(( $(date +%s) - T0 )) s"
uv pip install -q --python .venv/bin/python -e ".[test]" 2>&1 | tail -2 || true
date -Is
echo "BUILD END rc=0"
