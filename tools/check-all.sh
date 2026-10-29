#!/usr/bin/env bash
# Usage: bash tools/check-all.sh  (from any directory; uses Rust 1.93 and .venv)
# Full local checks from CONTRIBUTING.md, including the core crate.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH=$HOME/.cargo/bin:$PATH
fail=0
step() { echo "## $1"; shift; "$@" || { echo "FAILED: $*"; fail=1; }; }
step root-build cargo +1.93 build --offline --release -q
step root-test bash -c "cargo +1.93 test --offline --release -q 2>&1 | grep -E \"^test result\" | head -1"
step root-clippy cargo +1.93 clippy --offline --all-targets -q -- -D warnings
step root-fmt cargo +1.93 fmt --check
step core-build cargo +1.93 build --offline --release -q --manifest-path core/Cargo.toml
step core-test bash -c "cargo +1.93 test --offline --release -q --manifest-path core/Cargo.toml 2>&1 | grep -E \"^test result\" | head -1"
step core-clippy cargo +1.93 clippy --offline --all-targets -q --manifest-path core/Cargo.toml -- -D warnings
step core-fmt cargo +1.93 fmt --check --manifest-path core/Cargo.toml
step ruff .venv/bin/ruff check python examples tests
step ruff-format .venv/bin/ruff format --check python examples tests
step diff-check git diff --check
step pytest bash -c ".venv/bin/python -m pytest -q 2>&1 | tail -2"
echo "## overall: $([ $fail = 0 ] && echo PASS || echo FAIL)"
exit $fail
