# Contributing to Rang

Contributions should make a scientific claim easier to reproduce, test or reject. Use Rust for numerical kernels and Python for interfaces, experiments and analysis.

## Local checks

Create the Python environment described in the README, then run all checks before committing:

```sh
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -e '.[pointing,beam,test]' ruff maturin  # needs cargo on PATH
cargo build --offline --release
cargo test --offline --release
cargo clippy --offline --all-targets -- -D warnings
cargo fmt --check
cargo build --offline --release --manifest-path core/Cargo.toml
cargo test --offline --release --manifest-path core/Cargo.toml
cargo clippy --offline --all-targets --manifest-path core/Cargo.toml -- -D warnings
cargo fmt --check --manifest-path core/Cargo.toml
.venv/bin/maturin develop --release --offline
cargo clippy --offline --all-targets --manifest-path core/py/Cargo.toml -- -D warnings
cargo fmt --check --manifest-path core/py/Cargo.toml
.venv/bin/python -m pytest -q
.venv/bin/ruff check python examples tests
.venv/bin/ruff format --check python examples tests
git diff --check
```

`bash tools/check-all.sh` runs all of the above with Rust 1.93 and reports
PASS or FAIL per step.

The PyO3 crate `core/py` has no `cargo test`: an extension-module cdylib
cannot link a test binary, so it is tested from Python
(`tests/test_core_backends.py`, which checks both backends give identical
bytes).

Supported hosts are Linux and macOS. Native Windows is not supported: the
fresh-namespace, symlink and disk-budget guards rely on POSIX semantics, and 40
tests fail there for that reason alone. On Windows, use a WSL2 Linux checkout on
the Linux filesystem (not `/mnt/c`) with Docker inside WSL. Use Rust 1.93, which
matches the container kernel stage, so the Rust sources recorded in the result
receipts remain unchanged: `cargo +1.93 ...` with the commands above. Newer
Clippy releases add lints that would otherwise require kernel edits.

## Scientific reporting

Use fenced `math` blocks for display equations and dollar-delimited LaTeX for
inline mathematics, following [GitHub's math formatting](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/writing-mathematical-expressions).
Keep code identifiers in code spans rather than math delimiters.

The optional JAX tests are skipped when JAX is absent. Install the `pointing`
extra as above for full verification. JAX is the explicitly requested
automatic-differentiation reference path alongside the Rust core.

- Separate proposals, implemented algorithms and measured results.
- Record seeds, configuration, tolerances, provenance and executable or source revision.
- Match sky assumptions, priors, observations and tuning effort between baselines.
- Report absolute flux error, signal response, residual distortion and held-out prediction separately.
- Distinguish realization scatter from posterior uncertainty and confidence intervals.
- Preserve failures and null results. Do not select only favorable seeds.
- Cite the closest primary literature and identify the specific difference being tested.

Generated campaigns belong in ignored `outputs/`. Retain compact numerical summaries and reproduction commands in `research/`. Do not commit observational data without documenting provenance and redistribution terms.

## Reporting an issue

Include the command, configuration and seed, expected and observed behavior, Rust/Python versions, and a minimal reproducer. For scientific discrepancies, include the relevant control and identify whether the metric is measured in visibility or image space.
