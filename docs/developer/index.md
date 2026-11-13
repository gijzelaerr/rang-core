# Developer guide

For algorithm scientists and software engineers who change rang and
contribute the change back, with or without an agent. The rules are in
{gh}`AGENTS.md`, Part 1; the pull-request route is {doc}`../contributing`;
what counts as a gain is {doc}`claims`.

## Architecture

```text
python/rang/             Python: command line, configuration, pipeline, notebooks, research drivers
   │  NumPy arrays borrowed in place, GIL released around every kernel
   ▼
core/py/  (rang-core-py) PyO3 extension rang._core; no kernel code, only bindings
   │  C ABI of rang_core::ffi*  (#[repr(C)] structs, explicit lengths, status codes)
   ▼
core/     (rang-core)    the kernels: MS reader and table writer, solvers, calibration,
                         SumThreshold, weights, gridders, GeMClean, predictor, GPU (feature gpu)
src/      (rang-sim)     the root crate: the pointing simulation, gain TV, projector, trend;
                         linked into the extension as rang_core::sim
```

- **Rust for kernels**, Python for interfaces, orchestration and experiment
  scripts. A new numerical kernel goes in `core/src/`, gets a C-ABI function
  in an `ffi_*.rs`, a binding in `core/py/src/`, and a thin wrapper in
  `python/rang/core_*.py` or `cal_*.py`. Importing `rang` never runs Cargo
  ({gh}`research/p7-architecture.md`).
- **GPU where it pays**, behind the core's `gpu` feature (wgpu). Every GPU path
  has a CPU path with the same result within a written tolerance; the wheels
  are CPU only ({gh}`research/x2-wgpu.md`).
- **Telescope specifics** stay behind `python/rang/meerkat.py` and the
  refusals of {gh}`research/w4-unsupported.md`; nothing is generalised before
  a second telescope's data and oracle exist ({gh}`research/meerkat-scope.md`).
- **The JAX path** of the pointing solver (`rang.pointing`, the `pointing`
  extra) is a deliberate reference implementation beside the Rust baseline.

### Where things are

| Path | What |
| --- | --- |
| `python/rang/core_cli.py`, `core_config.py`, `core_pipeline.py`, `core_writeback.py` | the command line, the configuration schema and refusals, the stages and resume, write-back with flag versions and a journal |
| `python/rang/cal_*.py`, `applycal.py`, `calmodels.py` | the calibration terms, apply, calibrator models |
| `python/rang/formats/` | CASA tables, flag versions, QuartiCal stores, sky models, H5parm, killMS |
| `python/rang/notebook/` | what the notebooks import: data, plots, the frozen rules they quote |
| `core/src/cal/`, `solve.rs`, `fused.rs` | CASA-style solves and apply; QuartiCal's `complex` solver; the fused residual pass |
| `core/src/ms*.rs`, `tiled.rs`, `ism.rs`, `aipsio.rs` | the casacore table reader and writer |
| `core/src/sumthreshold.rs`, `weights.rs`, `grid.rs`, `wgridder.rs` | Tricolour, WSClean weights, w-stacking, ducc0's wgridder |
| `core/src/gemclean/`, `clean*.rs` | GeMClean and the CLEAN study |
| `history/` | the frozen campaigns: recipes, containers and modules, not edited |
| `research/` | the notes and compact result archives; `tests/` reads some of them |
| `formal/` | Lean proofs of the CLEAN theory ({gh}`research/clean-theory.md`) |

The {doc}`../concepts/index` pages give each port with its oracle; the
{doc}`../api/index` is generated from the docstrings.

## Build

From a checkout, with Rust 1.93 and `cargo` on `PATH` ({doc}`../installation`,
"From source"):

```sh
python -m pip install --index-url https://pypi.org/simple \
    -e '.[pointing,beam,test,imaging,formats,notebook,docs]' ruff maturin
maturin develop --release        # after every Rust change; Python never runs Cargo
```

A build from a checkout targets x86-64-v3 (`.cargo/config.toml`); set
`RUSTFLAGS="-C target-cpu=x86-64"` for a CPU without AVX2 and FMA, as the
wheels do. The GPU paths: `cargo test --release --manifest-path core/Cargo.toml
--features gpu`, and `maturin develop --release --features gpu` for the
extension.

## Test

```sh
python -m pytest -q                 # or -n 8 with pytest-xdist
python -m rang.check                # every check before a commit: fmt, clippy, cargo test, ruff, pytest, ...
```

`python -m rang.check` (also `rang-core check`, `bash tools/check-all.sh`)
runs every Rust and Python step and prints PASS or FAIL per step and
`overall: PASS`; {doc}`../contributing` lists the steps. Some tests read
archived outputs or need an oracle (CASA, QuartiCal, WSClean) and skip
without them; CI has neither, so their gates run only in this local check,
and a pull request reports its result. On a shared host run it under
`python tools/heavy_lock.py run --slots N --mem G -- ...`.

The docs: `python docs/execute_notebooks.py` (optional; needs the public
fixture), then `sphinx-build -W --keep-going -b html docs docs/_build/html`,
which must build without a warning. `docs/cli.md` is generated:
`python docs/gen_cli.py` after a change to a help text.

## Conventions that tests enforce

- Every source file starts with an SPDX line; a port names the upstream
  licence too and keeps its notice ({gh}`tests/test_spdx_headers.py`,
  {doc}`../licence`).
- The version is written once, in `pyproject.toml`
  ({gh}`tests/test_w4_5_release.py`).
- Every note in `research/` is linked from `research/README.md`; the README
  stays short, with absolute links ({gh}`tests/test_w4_8_docs.py`).
- Every repository link on this site names a file that exists
  ({gh}`tests/test_d1_docs.py`).
- Verbatim extracts of frozen modules stay byte-identical
  ({gh}`tests/test_p11_extract.py`).

## With an agent

Open any agent in a checkout; `AGENTS.md` is written for it. The task
procedures are in {doc}`../agents/index`: {doc}`../agents/propose-and-measure`
for an algorithm change, {doc}`../agents/image-a-meerkat-ms` and
{doc}`../agents/answer-a-question` for the other audiences. Claude Code also
finds them as skills in `.claude/skills/`.
