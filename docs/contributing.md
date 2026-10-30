# Contributing

Contributions should make a scientific claim easier to reproduce, test or
reject. The full guide is {gh}`CONTRIBUTING.md`; the working conventions are
in {gh}`AGENTS.md`.

## Languages

Rust for numerical kernels and performance-sensitive simulation and
calibration work; Python for astronomer-facing interfaces, experiment
scripting and orchestration. The JAX direct-Fourier and automatic
differentiation path of the pointing solver is a deliberate reference
implementation beside the Rust baseline. Install from public PyPI only.

## Checks

Build the environment as in {doc}`installation` (from source), then run every
check before committing:

```sh
bash tools/check-all.sh          # or: rang-core check, python -m rang.check
```

It runs, with Rust 1.93: build, test, clippy (`-D warnings`) and `fmt
--check` for the root crate and the core crate; `maturin develop --release`
and clippy and fmt for the extension crate; ruff and `ruff format --check`;
`git diff --check`; and pytest. It prints PASS or FAIL per step and
`overall: PASS` at the end, and takes a lock so that only one runs at a time
on a shared host. On Windows run `.venv\Scripts\python -m rang.check`.
Rebuild the extension with `maturin develop --release` after a Rust change;
Python never runs Cargo.

This site builds with:

```sh
pip install -e '.[docs,notebook,imaging,pointing,beam]'
python docs/execute_notebooks.py      # optional; needs the fixture
sphinx-build -W --keep-going -b html docs docs/_build/html
```

`python docs/gen_cli.py` regenerates {doc}`cli` after a change to the command
line; a test fails when the page and the help texts differ.

## Scientific reporting

- Separate proposals, implemented algorithms and measured results.
- Freeze a protocol (hypothesis, data, settings, acceptance criteria) in a
  commit before the code that tests it; label every later change post hoc.
- Record seeds, configuration, tolerances, provenance and the source
  revision. Match sky assumptions, priors, observations and tuning effort
  between baselines.
- Report absolute flux error, signal response, residual distortion and
  held-out prediction separately, and distinguish realisation scatter from
  posterior uncertainty.
- Preserve failures and null results; do not select favourable seeds.
- Novelty must mean demonstrably better calibration or imaging at comparable
  cost, or comparable quality at materially lower cost, against a relevant
  state-of-the-art method. Toy-baseline wins and reimplementations do not
  establish it.
- Cite the closest primary literature and name the difference being tested.

Generated campaigns belong in ignored `outputs/`; keep compact numerical
summaries and reproduction commands in `research/`. Do not commit
observational data without documenting provenance and redistribution terms.

## Reporting an issue

Include the command, configuration and seed, expected and observed
behaviour, Rust and Python versions, and a minimal reproducer. For a
scientific discrepancy include the relevant control and say whether the
metric is measured in visibility or image space. Issues go to
[gijzelaerr/rang-core](https://github.com/gijzelaerr/rang-core/issues).
