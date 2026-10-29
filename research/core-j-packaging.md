# Rang core, task J: PyO3/maturin packaging

Protocol frozen 2026-10-29 in the commit that adds this file, before any
extension code was written (the crate skeleton that existed at the freeze
held only an empty `#[pymodule]`, created to run `cargo fetch` once and
record the crate versions and licences below). Status: **proposed**. Task J
of wave 2 in [core-parallel-plan.md](core-parallel-plan.md); the row
"PyO3/maturin packaging, CI, container update" of
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9, deferred by [core-phase1.md](core-phase1.md). A packaging change;
under AGENTS.md it is not a scientific contribution, and no archived result
may change because of it.

## Question

Can the Rust core be built as a PyO3 extension module through maturin,
installable with `pip install -e .` from public PyPI and crates.io, with
NumPy arrays crossing the boundary without a copy where the C ABI already
passes pointers, while the C ABI and the `RANG_CORE_LIB` ctypes path keep
working, and do the archived core results reproduce bit-identically through
the new path?

## Design (proposed)

**Architecture.** A thin new crate `core/py` (package `rang-core-py`,
GPL-3.0-or-later, cdylib only) depends on `rang-core` as an rlib and on
`pyo3` and `numpy` from crates.io. It builds the extension module
`rangtoy._core` with the stable ABI (`abi3-py310`, matching
`requires-python >= 3.10`), so one binary serves the 3.14 development venv
and the 3.13 venv the frozen Stimela recipes need. `core/` itself is not
edited: its `rlib + cdylib` C ABI (`core/src/ffi*.rs`) stays the ctypes path,
built by `cargo build --offline --release` as before, and `RANG_CORE_LIB`
keeps selecting a prebuilt library.

Every extension function is a second entry door into the *same* `ffi_*`
function: it extracts the NumPy arrays as read-only or read-write slices
(`numpy::PyReadonlyArray`, `PyReadwriteArray`, which borrow the array's
buffer in place and refuse non-contiguous arrays), fills the `#[repr(C)]`
input and output structs of `ffi.rs`, `ffi_weights.rs`, `ffi_grid.rs` and
`ffi_flag.rs` with the slice pointers, calls the `rang_core_*` function and
returns its status code. No kernel code is duplicated, so bit identity with
the ctypes path follows by construction and the comparators only confirm
it. The Measurement Set reader (`ffi_ms.rs`, whose C ABI allocates buffers
the caller frees) is wrapped as a `#[pyclass]` over `ms::Table` whose
`read` moves the column bytes into a NumPy array without a copy
(`PyArray::from_vec`) and packs strings exactly as the C ABI does, so the
Python decoding is shared. Blosc payloads cross as `bytes` (zero-copy
`&[u8]`), decoded output is written into caller-owned NumPy buffers or
built in place with `PyBytes::new_with`.

**Wrappers.** `python/rangtoy/core.py` gains `backend_name()` and
`extension()`; every wrapper (`core.py`, `core_zarr.py`, `core_weights.py`,
`core_grid.py`, `core_flag.py`, `core_ms.py`) keeps its validation,
`np.require` casts and output allocation unchanged and dispatches only the
final call: the extension when active, the ctypes symbols otherwise. The
policy, in this order:

1. `RANG_CORE_BACKEND=extension` forces the extension (an error if it is
   not built); `RANG_CORE_BACKEND=ctypes` forces ctypes.
2. Otherwise, if `RANG_CORE_LIB` is set, ctypes loads that library: an
   explicit library wins over an implicit extension, so archived receipts
   and the phase 2 validator's cost subprocess keep their meaning.
3. Otherwise the extension is used when `rangtoy._core` imports, and ctypes
   (with the offline Cargo build) when it does not.

`library_path()` reports the active backend's binary, so provenance hashes
(`core_library_sha256` in the imaging replay and the gridder run) record
what ran.

**Packaging.** `pyproject.toml` switches the build backend from setuptools
to maturin (`[tool.maturin]`: `python-source = "python"`,
`manifest-path = "core/py/Cargo.toml"`, `module-name = "rangtoy._core"`),
keeping the project metadata, extras and the `rang-core` script. `pip
install -e .` (through `uv pip install -e .`) then builds the extension with
the cargo on `PATH` and places `python/rangtoy/_core.abi3.so` into the
source tree, which is ignored by git. The null-result clause below applies
if the mixed layout cannot be expressed.

**Checks.** `tools/check-all.sh` gains three steps between the core crate
and ruff: `ext-build` (`maturin develop --release --offline`, which builds
the extension and installs it into `.venv`, so pytest afterwards exercises
it), `ext-clippy` and `ext-fmt` on `core/py`. The crate has no `cargo test`
step because an `extension-module` cdylib cannot link a test binary; its
behaviour is tested from Python. `tools/core-j-suite.sh` (added at the
freeze) runs every driver and comparator below through the backend
`RANG_CORE_BACKEND` names, with `/usr/bin/time` per step.

**Crates fetched once from crates.io (2026-10-29), all permissive:**

| Crate | Version | Licence | Role |
| --- | --- | --- | --- |
| pyo3, pyo3-ffi, pyo3-macros, pyo3-macros-backend, pyo3-build-config | 0.30.1 | MIT OR Apache-2.0 | bindings; MSRV 1.85 |
| numpy | 0.30.0 | BSD-2-Clause | NumPy C API views; MSRV 1.85 |
| ndarray | 0.17.2 | MIT OR Apache-2.0 | numpy's dependency |
| num-complex 0.4.6, num-traits 0.2.19, num-integer 0.1.47, matrixmultiply 0.3.11, rawpointer 0.2.1 | – | MIT OR Apache-2.0 | ndarray's dependencies |
| libc 0.2.191, once_cell 1.21.4, portable-atomic 1.15.0, portable-atomic-util 0.2.8, rustc-hash 2.1.3, heck 0.5.0, autocfg 1.5.1 | – | MIT OR Apache-2.0 | pyo3's dependencies |
| syn 3.0.9, quote 1.0.47, proc-macro2 1.0.107, unicode-ident 1.0.27 | – | MIT OR Apache-2.0 | proc macros |
| target-lexicon | 0.13.5 | Apache-2.0 WITH LLVM-exception | build config |

`core/py/Cargo.lock` is committed; `cargo fetch` took 3.3 s. maturin 1.16.0
comes from public PyPI into `.venv`.

## Inputs (frozen)

The archives and run directories of the merged tasks, read-only:

| Task | Driver and comparator | Archive or oracle |
| --- | --- | --- |
| phase 2 | `examples/validate_core_phase2.py` | QuartiCal gains in `outputs/tv-response-wsl-20261029-01` and `outputs/luno-solve-20261029-02`; `results/core-phase2.json` |
| section 6 | `examples/prototype_section6.py`, `examples/check_section6.py` | `outputs/core-section6-oracle-20261029-01`; `results/core-section6.json` |
| actions | `examples/run_core_campaign.py actions`, `examples/compare_core_actions.py` | `outputs/core-phase3-actions-inputs-20261029-01`; `results/gain-tv-actions.json` |
| B | `examples/compare_core_weights.py --tolerance 4.76837158203125e-07` | `outputs/core-b-20261030-01/oracle` (linked into the fresh directory) |
| C | `examples/run_core_gridder.py`, `examples/compare_core_gridder.py` | `outputs/core-c-20261029-01`, archive images `outputs/tv-next-imaging-wsl-20261029-01/images` |
| D | `examples/run_core_flags.py`, `examples/compare_core_flags.py run` | `outputs/core-d-oracle-20261029-01/run`, `outputs/tv-caracal-wsl-20261029-01`, `outputs/caracal-strategy-inputs-8f7bb363` |
| E | `examples/check_ms_reader.py` | `outputs/core-e-oracle-20261029-01` |
| I | `examples/run_core_imaging.py` (both comparisons) | `outputs/tv-next-imaging-wsl-20261029-01`, `outputs/core-c-20261029-01/inputs`; `results/gain-tv-next-imaging.json` |

## Precondition: the comparators on the ctypes path (measured before the freeze)

`RANG_CORE_BACKEND=ctypes bash tools/core-j-suite.sh outputs/core-j-20261029-00-ctypes`
on origin/main `2e02ad4`, cdylib built by `cargo +1.93` (the toolchain
`tools/check-all.sh` uses; `RUSTUP_TOOLCHAIN=1.93` exported so that the
import-time build matches), load average 0.7–2.9, nothing else running.

| Step | Wall | Peak RSS | Outcome on the ctypes path |
| --- | ---: | ---: | --- |
| phase 2 validator | 2.4 s | 128 MB | all 11 checks pass (fixture and LUNO gains, losses, TV, survey, side effects; cost 0.51 s, 96 MB) |
| section 6 prototype + checker | 7.3 s + 18.4 s | 143 MB, 637 MB | criteria 1–7 and 9–11 pass; **criterion 8 failed**: 2.41 s excluding decode against 2.0 s, with a cold page cache (first touch of the 752 MB of chunk spans since the host restarted). Labelled repeat with a warm cache (`section6-warm`, 4.5 s): all eleven pass, 1.45 s excluding decode, 143 MB. The gate for task J is therefore the warm repeat; the suite now passes the measured RSS to the checker (the first run passed the 200 MB limit as the value, a script slip fixed before the freeze) |
| actions + comparator | 5.1 s + 0.02 s | 240 MB | 0 failures: 61 exact, 102 floats (6.6e-15), 24 differences (1.8e-11); inputs and `git status` unchanged |
| B comparator | 0.9 s | 83 MB | criteria 1–5 pass; weights identical (0 relative), sums 1.8e-15 |
| C run + pixel comparator | 52.7 s + 0.3 s | 139 MB | criteria 1–3 pass; dirty 6.1e-7 and PSF 4.2e-7 of peak against the archive, WCS equal (task C's post-hoc numbers) |
| D run + comparator | 8.9 s + 0.4 s | 98 MB | criteria 1–5 pass (flags equal for all four controls) |
| E checker | 0.7 s | 156 MB | criteria 1–3 pass, 0 failures on 173 columns |
| I replay (both comparisons) | 53.0 s | 214 MB | 0 failures against the archive and the host reproduction (532 exact; fluxes 1.4e-7, responses 1.3e-7, PSF 8.9e-8, closures 3.1e-8); the first run's audit reported `git status` changed because the operator wrote this file during it, so it was repeated (`i-rerun`, 52.7 s) with the tree untouched: inputs and `git status` unchanged |

Receipts: `outputs/core-j-20261029-00-ctypes/<step>/…`, `timings.tsv` and
`<step>.log` there. Every gated criterion of every task passes on the ctypes
path at `2e02ad4`, so the comparators are fit to judge the extension.

## Acceptance criteria (frozen)

Gated, decided here:

1. **Build and install.** From the worktree, `uv pip install --index-url
   https://pypi.org/simple -e '.[pointing,beam,test,imaging]'` with cargo on
   `PATH` succeeds with no private index and no vendored crate, and
   `python -c "import rangtoy._core"` works in that venv. `tools/check-all.sh`
   passes with the three new steps, offline (`--offline` on every cargo and
   maturin call).
2. **C ABI kept.** `cargo +1.93 build --offline --release` of `core/` still
   produces `librang_core.so` with every `rang_core_*` symbol it had at
   `2e02ad4` (compared with `nm -D`), `core/src` is unchanged, and the
   suite passes with `RANG_CORE_BACKEND=ctypes` after the change exactly as
   in the precondition (same criteria, same class counts).
3. **Backend selection.** A unit test checks the three rules of the policy:
   `RANG_CORE_BACKEND=ctypes` never imports `rangtoy._core`;
   `RANG_CORE_BACKEND=extension` never calls `core.library()` (so no cargo
   build and no `ctypes.CDLL`); with neither set and `RANG_CORE_LIB` set,
   ctypes loads that path; with none set the extension is chosen when it
   imports.
4. **Zero copy.** For every NumPy dtype the wrappers pass (`float32`,
   `float64`, `uint8`, `int8`, `uint32`, `int32`, `uint64`/`uintp`),
   the address the extension sees for an array (`_core.data_address`,
   the same `as_slice()` path every function uses) equals
   `array.ctypes.data`, and every output array a wrapper allocates is
   returned as the same object it allocated (filled in place). Read-only
   and non-contiguous arrays are rejected by the extension, not copied.
5. **Unit-level bit identity.** On randomised small cases,
   `tests/test_core_backends.py` runs every wrapper function (`fused_pass`,
   `solve_complex`, `predict_components`, `blosc_decode`,
   `blosc_decode_rows`, `core_zarr.read_rows` and `header_fields`,
   `core_weights.stokes_i`, `imaging_weights`, `padded_size`, `grid_shape`,
   `core_grid.kernel`, `invert`, `core_flag.flag_rows`, `core_ms.Table`
   on the fixture MS when present) under both backends and requires every
   output array byte-equal (`tobytes()`), every scalar equal, and the same
   exception class and message on the same invalid inputs (one invalid case
   per function).
6. **Archive bit identity.** `RANG_CORE_BACKEND=extension bash
   tools/core-j-suite.sh outputs/core-j-<date>-NN` (with `RANG_CORE_LIB`
   unset) passes every gated criterion of every driver and comparator in
   the table above against its archive, with the same outcomes as the
   precondition (a criterion that failed as frozen there for a reason
   unrelated to the backend, such as a cost limit, is reported with its
   numbers and is not a failure of this criterion if it fails here for the
   same reason). In addition, `examples/compare_core_backends.py` compares
   the extension suite's directory with the precondition's file by file:
   every `.npz` array byte-equal, every FITS image's data and header cards
   equal, every JSON leaf equal except the volatile keys it lists (wall
   times, RSS, dates, run paths, library hashes, interpreter and backend
   names, load), and no file missing on either side. Zero differences is
   the gate.
7. **No side effects.** The drivers' own audits pass (inputs and `git
   status` unchanged); the extension suite writes only into its fresh
   directory and `maturin develop` writes only `python/rangtoy/_core*.so`
   (ignored) and the venv.

Reported, not gated:

8. **Cost.** Wall time of the extension build (cold and warm cache, `maturin
   develop --release`), the wheel's size, the time of `import rangtoy.core`
   plus the first kernel call under each backend (the ctypes path pays the
   offline Cargo build and `cargo metadata` at import), and the per-call
   boundary overhead on a small fused pass (1000 repetitions, both
   backends), with `/usr/bin/time` where a process is timed; all logged in
   the timing table below.

A failure of any of 1–7 is recorded here with its numbers and is not
hidden; post-hoc changes are labelled. Task J is reported as "implemented;
measured" only if 1–7 pass as frozen.

**Null-result clause.** If maturin cannot express the layout (the Python
package in `python/`, the extension crate in `core/py`, the root `rang-toy`
crate beside `pyproject.toml`) without moving files that archived receipts
and frozen recipes name, this file records which constraint fails and
proposes the restructuring under "For the coordinator" instead of doing it;
the setuptools build and the ctypes path then stay as they are.

## Timings

| Date | Step | Wall | Peak RSS | Notes |
| --- | --- | --- | --- | --- |
| 2026-10-29 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 3.9 s | – | uv cache warm; numpy 2.5.4, maturin 1.16.0 |
| 2026-10-29 | `cargo +1.93 build --release` core and root crates, `CARGO_BUILD_JOBS=8` | 2.6 s + 1.0 s | – | before any task J code |
| 2026-10-29 | `cargo +1.93 fetch` of the `core/py` skeleton (pyo3 0.30.1, numpy 0.30.0 and 22 dependencies) | 3.3 s | – | the only network use of the crate build |
| 2026-10-29 | precondition suite on ctypes, `tools/core-j-suite.sh outputs/core-j-20261029-00-ctypes` (the table above) | about 150 s | 637 MB (checker) | load 0.7–2.9; section 6 cold-cache cost failure, warm repeat 4.5 s + 18.2 s; task I repeat 52.7 s |
