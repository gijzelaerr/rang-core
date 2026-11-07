#!/usr/bin/env bash
# rust_tests.sh : fmt, the gemclean unit tests and clippy of the core crate (development loop).
set -uo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin
cd $HOME/Worktrees/rang/fp-g9-stokes/core
cargo +1.93 fmt
cargo +1.93 test --offline --release --lib gemclean 2>&1 | grep -E "test result|FAILED|panicked|error" | head -30
cargo +1.93 test --offline --release --bin gemclean 2>&1 | grep -E "test result|FAILED|panicked|error" | head -10
cargo +1.93 clippy --offline --all-targets -- -D warnings 2>&1 | grep -E "^(error|warning)" -A8 | head -60
