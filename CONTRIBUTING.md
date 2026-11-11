# Contributing to Rang

Contributions should make a scientific claim easier to reproduce, test or reject. Use Rust for numerical kernels and Python for interfaces, experiments and analysis. The documentation is at <https://pythonic.nl/rang-core/>.

## The pull-request route

The owner commits to `main`; everyone else, people and their coding agents
alike, contributes through pull requests. The working rules for both are in
`AGENTS.md`, Part 1 (Part 2 is the owner's own and does not apply to you).

1. **Open an issue or a draft pull request first** for anything larger than a
   fix, so the owner can say whether it fits `research/vision.md`.
2. **Branch** from current `main` (or fork). One topic per pull request.
3. **For a scientific or performance claim, freeze a proposal note first:**
   commit `research/<id>-<name>.md` with the hypothesis, data, oracle, frozen
   tolerances and the decision rule before the code that tests it. The
   measurement, its seeds, run paths and receipts go in the same note under
   "Measured result"; nulls and failures are reported, not dropped. The
   novelty rule (`AGENTS.md`, "Claims") decides what may be called a gain.
   `docs/agents/propose-and-measure.md` is the procedure.
4. **Run the full local checks** below (`python -m rang.check`), under
   `python tools/heavy_lock.py run -- ...` on a shared host, and paste the
   summary (`overall: PASS`, or the failing steps) into the pull request.
5. **CI.** The `tests` workflow runs on every pull request: ruff, ruff format,
   cargo fmt, clippy (warnings are errors), cargo test for the root crate and
   `core/`, and pytest on Linux and Windows against the branch's extension.
   The `docs` workflow also runs on every pull request: it builds the
   extension, executes the notebooks on the public fixture, checks the CLI page
   and builds the site with `sphinx-build -W`. The `wheels` workflow (five
   platforms) runs when the pull request touches `core/`, `src/`, `Cargo.*`,
   `.cargo/`, `pyproject.toml` or `tools/wheel/`, and tests each built wheel
   with a subset of the Python tests. CI has no archives or oracles (CASA,
   QuartiCal, WSClean), so their gates run only in step 4, which must be done
   and reported.
6. **Describe** what changed, what was measured and what was not checked.
   The owner reviews and merges; defaults and scientific status change only on
   the owner's decision.

**Agents.** Any agent may do these steps for you; it commits under your name
and address, not a bot identity. Point it at `AGENTS.md` and at the task
procedures in `docs/agents/` (Claude Code also finds them as skills in
`.claude/skills/`).

## Local checks

Create the Python environment described in the README, then run all checks before committing. The optional tests use every extra below; with fewer, more of them skip:

```sh
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -e '.[pointing,beam,test,imaging,formats,casacure,docs,notebook]' ruff maturin  # needs cargo on PATH
cargo build --offline --release
cargo test --offline --release
cargo clippy --offline --all-targets -- -D warnings
cargo fmt --check
cargo build --offline --release --manifest-path core/Cargo.toml
cargo test --offline --release --manifest-path core/Cargo.toml
cargo clippy --offline --all-targets --manifest-path core/Cargo.toml -- -D warnings
cargo fmt --check --manifest-path core/Cargo.toml
cargo clippy --offline --all-targets --manifest-path core/Cargo.toml --features gpu -- -D warnings
cargo test --offline --release --manifest-path core/Cargo.toml --features gpu  # GPU tests skip without an adapter
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

The steps `core-clippy-gpu` and `core-test-gpu` build the core's `gpu`
feature (wgpu): about 6 minutes cold, a few seconds warm. Leave them
out with `rang-core check --skip core-clippy-gpu,core-test-gpu`.
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

Linux, macOS and Windows are native build and CI targets: `wheels.yml` builds
and tests Linux x86_64 and aarch64, macOS arm64 and x86_64, and Windows x86_64
(`research/x1-crossplatform.md`). Some tests skip on Windows: those of the
frozen modules that need `st_blocks` or a POSIX container path, symlinks without
Developer Mode, the simulation's Linux-archived bytes and absent archives. The frozen
campaigns' fresh-namespace and disk-budget guards still rely on POSIX semantics.

Development and the full check run natively on Windows (2026-11-09, main
`91392bd`). Clone after `.gitattributes` existed, or with `core.autocrlf false`:
a checkout older than it keeps CRLF files and fails the verbatim-copy tests. Install the
test extras (`astropy`, `h5py`, `matplotlib`, `jax`, `scipy`, `katbeam`, `eidos`) or
their tests fail on import. The gain-hash gate reads the archive from
`RANG_ARCHIVE_OUTPUTS` (on the development host the WSL checkout's
`\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs`). On a host shared by
Windows and WSL, take the heavy-job lock with
`python tools/heavy_lock.py run -- <command>` from either side; `flock` inside
WSL is invisible to Windows processes.
Linux-only oracles (CASA, WSClean, QuartiCal, CARACal, Tricolour,
python-casacore) stay in WSL.
For campaign work on Windows, use a WSL2 Linux checkout on
the Linux filesystem (not `/mnt/c`), with Docker inside WSL only to re-run the
frozen campaigns in `history/` (`history/README.md`). Use Rust 1.93, which
matches the container kernel stage, so the Rust sources recorded in the result
receipts remain unchanged: `cargo +1.93 ...` with the commands above. Newer
Clippy releases add lints that would otherwise require kernel edits.

## Licence headers

Every tracked `.py`, `.rs`, `.sh` and `.cc` file under `python/rang`,
`core/src`, `src` and `tools` starts with an SPDX line, after a shebang or
encoding line if it has one:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
```

(`//` for Rust and C++). A file ported from code under another licence names
both, for example `GPL-3.0-or-later AND MIT`, and keeps the upstream notice
in full (`docs/licence.md` lists the ported code). Longer copyright
notices may follow the SPDX line. `tests/test_spdx_headers.py` checks it.

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
carries only the crates, `data/README.md` and `data/meerkat.itrf.txt`,
`python/`, `tests/`, `tools/wheel/`, README, CHANGELOG, `CITATION.cff`,
LICENSE and `THIRD-PARTY-NOTICES.txt` (`[tool.maturin] exclude` in
`pyproject.toml`).

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
