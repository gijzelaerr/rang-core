set -e
cd ~/Worktrees/rang/e2a-3b-k
date -Is; cut -d" " -f1-3 /proc/loadavg
uv venv --python 3.14 .venv
for m in Cargo.toml core/Cargo.toml core/py/Cargo.toml; do cargo +1.93 fetch --manifest-path $m >/dev/null; done
uv pip install --python .venv/bin/python maturin numpy pytest pyyaml scipy >/dev/null
grep -n "optional-dependencies" -A30 pyproject.toml | head -0
. .venv/bin/activate
T0=$(date +%s)
CARGO_BUILD_JOBS=4 maturin develop --release -m core/py/Cargo.toml 2>&1 | tail -3
echo "maturin $(( $(date +%s) - T0 )) s"
uv pip install --python .venv/bin/python -e ".[test]" 2>&1 | tail -2 || true
date -Is; cut -d" " -f1-3 /proc/loadavg
