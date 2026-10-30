#!/usr/bin/env bash
# Usage: bash tools/check-all.sh [--rust | --python | --all]  (from any directory; uses Rust 1.93 and .venv)
# Full local checks from CONTRIBUTING.md, including the core crate. The steps
# live in python/rang/check.py (`rang-core check`, research/p9-cli.md), which
# runs them portably; on Windows run `.venv\Scripts\python -m rang.check`.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH=$HOME/.cargo/bin:$PATH
# One check-all at a time on a shared host (research/p10-tests.md); RANG_CHECKALL_LOCK overrides.
# Call this script plainly: it locks itself. Wrapping it in an outer flock on the
# same file deadlocks (set RANG_CHECKALL_LOCKED=1 if you must wrap it).
lock=${RANG_CHECKALL_LOCK:-$HOME/.rang-checkall-v2.lock}
if [ -z "${RANG_CHECKALL_LOCKED:-}" ]; then
  export RANG_CHECKALL_LOCKED=1
  exec flock "$lock" bash "$0" "$@"
fi
exec .venv/bin/python -m rang.check "$@"
