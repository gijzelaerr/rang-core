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

`rang-core check [--rust|--python|--all]` (or `python -m rang.check`, which
is what `tools/check-all.sh` runs) is the same check on any platform; on
Windows run `.venv\Scripts\python -m rang.check`.
`bash tools/check-all.sh` runs all of the above with Rust 1.93 and reports
PASS or FAIL per step. Optional packaging check: `bash tools/wheel/build.sh
outputs/wheel-<date>-NN` builds the manylinux wheel in docker and
`bash tools/wheel/test.sh outputs/wheel-<date>-NN outputs/wheel-<date>-MM`
installs it on clean CPython 3.10–3.14; `pytest` of the source tree tests
the editable build, `tools/wheel/test.sh` the installed wheel.

The PyO3 crate `core/py` has no `cargo test`: an extension-module cdylib
cannot link a test binary, so it is tested from Python
(`tests/test_core_backends.py` compares it with the archive of the retired
ctypes oracle, `tests/test_p7_architecture.py` checks no cargo at run time,
the GIL release and panic handling). Python never runs Cargo: rebuild the
extension with `maturin develop --release --offline` after a Rust change.

Supported hosts are Linux and macOS. Native Windows runs the test suite since
task P7 (622 passed, 43 skipped: tests of the frozen modules that need
`st_blocks` or a POSIX container path, symlinks without Developer Mode, the
toy's Linux-archived bytes and absent archives; `research/p7-architecture.md`),
but the frozen campaigns' fresh-namespace and disk-budget guards still rely
on POSIX semantics. For campaign work on Windows, use a WSL2 Linux checkout on
the Linux filesystem (not `/mnt/c`), with Docker inside WSL only to re-run the
frozen campaigns in `history/` (`history/README.md`). Use Rust 1.93, which
matches the container kernel stage, so the Rust sources recorded in the result
receipts remain unchanged: `cargo +1.93 ...` with the commands above. Newer
Clippy releases add lints that would otherwise require kernel edits.

## Releasing

The version is set once, in `pyproject.toml` `[project] version`; bump the
three `Cargo.toml` package versions with it and refresh the three lock files
with `cargo metadata --offline --format-version 1 > /dev/null` in `.`,
`core/` and `core/py/` (CI builds with `--locked`).
`tests/test_w4_5_release.py` checks that all
of them, `docs/conf.py` and `rang.__version__` agree. Move the `CHANGELOG.md`
entries from "Unreleased" into a section `## <version> (<date>)`, run the
full local checks, commit and push to `main`, then tag:
`git tag v<version> && git push origin v<version>`. The `wheels` workflow
refuses a tag that differs from the version (in both the release and the
publish job, before any upload), takes the release notes from the
changelog section, and publishes to PyPI by trusted publishing. The sdist
carries only the crates, `python/`, `tests/` and `tools/wheel/`
(`[tool.maturin] exclude` in `pyproject.toml`).

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
