#!/usr/bin/env bash
# Usage: bash tools/check-all.sh  (from any directory; uses Rust 1.93 and .venv)
# Full local checks from CONTRIBUTING.md, including the core crate.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH=$HOME/.cargo/bin:$PATH
# One check-all at a time on a shared host (research/p10-tests.md); RANG_CHECKALL_LOCK overrides.
lock=${RANG_CHECKALL_LOCK:-$HOME/.rang-checkall.lock}
if [ -z "${RANG_CHECKALL_LOCKED:-}" ]; then
  export RANG_CHECKALL_LOCKED=1
  exec flock "$lock" bash "$0" "$@"
fi
fail=0
step() { echo "## $1"; shift; "$@" || { echo "FAILED: $*"; fail=1; }; }
step root-build cargo +1.93 build --offline --release -q
rust_test() { local log; log=$(mktemp); cargo +1.93 test --offline --release -q "$@" > "$log" 2>&1; local s=$?; grep -E "^test result" "$log" | head -1; [ $s = 0 ] || cat "$log"; rm -f "$log"; return $s; }
step root-test rust_test
step root-clippy cargo +1.93 clippy --offline --all-targets -q -- -D warnings
step root-fmt cargo +1.93 fmt --check
step core-build cargo +1.93 build --offline --release -q --manifest-path core/Cargo.toml
step core-test rust_test --manifest-path core/Cargo.toml
step core-clippy cargo +1.93 clippy --offline --all-targets -q --manifest-path core/Cargo.toml -- -D warnings
step core-fmt cargo +1.93 fmt --check --manifest-path core/Cargo.toml
# The PyO3 extension rangtoy._core (research/core-j-packaging.md): built and
# installed into .venv by maturin so that pytest exercises it; no cargo test,
# because an extension-module cdylib cannot link a test binary.
step ext-build env RUSTUP_TOOLCHAIN=1.93 .venv/bin/maturin develop --release --offline -q
step ext-clippy cargo +1.93 clippy --offline --all-targets -q --manifest-path core/py/Cargo.toml -- -D warnings
step ext-fmt cargo +1.93 fmt --check --manifest-path core/py/Cargo.toml
step ruff .venv/bin/ruff check python examples tests
step ruff-format .venv/bin/ruff format --check python examples tests
step diff-check git diff --check
# pipefail inside the sub-shell, so a failing test fails the step.
step pytest bash -c "set -o pipefail; .venv/bin/python -m pytest -q 2>&1 | tail -2"
echo "## overall: $([ $fail = 0 ] && echo PASS || echo FAIL)"
exit $fail
