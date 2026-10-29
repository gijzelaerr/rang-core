# Rang core, task J: PyO3/maturin packaging

Protocol frozen 2026-10-29 in `d4f88c8`, before any extension code was
written (the crate skeleton that existed at the freeze held only an empty
`#[pymodule]`, created to run `cargo fetch` once and record the crate
versions and licences below). Status: **implemented; measured: criteria 1–7
pass as frozen** (the section 6 cost criterion, not a criterion of this
task, fails cold and passes warm under both backends, exactly as in the
precondition; see the measured result). Task J
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

## Implementation notes (after the freeze; the design above was followed)

- `core/py/src/lib.rs` (`rang-core-py`, 681 lines): seventeen functions and
  the `MsTable` class, each a few lines of pointer plumbing around the
  `rang_core_*` function it mirrors. Functions return the C status code
  (plus the values the C ABI writes through out-pointers, as a tuple), and
  the Python wrappers raise exactly as they do for ctypes. The `numpy` crate
  refuses non-contiguous inputs and read-only outputs with `TypeError`
  before any kernel runs. `MsTable.read` raises `OSError` with the same
  message the C ABI leaves in `rang_core_ms_last_error`.
- The extension binary exports the full C ABI as well: `nm -D` lists the
  same 22 `rang_core_*` symbols in `_core.abi3.so` and in
  `librang_core.so`, because `#[no_mangle]` items of the `rang-core` rlib are
  exported from any cdylib that links it. So `RANG_CORE_LIB=python/rangtoy/_core.abi3.so`
  is a valid ctypes library, and one binary can serve both paths; the unit
  test `test_backend_policy` uses this.
- `core_fetch.decode_slice` had called `rang_core_blosc_decode_span_rows`
  through `core_zarr._lib()` directly; it now calls the new
  `core_zarr.decode_span_rows`, which dispatches like the other wrappers.
  `core_ms` shares one `_decode` for both backends and skips the copy when
  the bytes are already owned (extension path).
- `pyproject.toml` builds with maturin; `[tool.setuptools]` is gone. The
  mixed layout needed no restructuring (null-result clause not triggered):
  maturin places `python/rangtoy/_core.abi3.so` and a `.pth` to `python/`
  for the editable install. `.gitignore` adds `/core/py/target/`,
  `/python/rangtoy/_core*.so` and `/python/rangtoy.egg-info/`.
- `core/src` is untouched (`git diff 2e02ad4 -- core/src core/Cargo.toml
  core/Cargo.lock` is empty).
- Not done, deliberately: the extension holds the GIL during kernel calls
  (ctypes releases it). No current driver calls the core from threads; see
  the open questions.
- **Post-hoc, after the first full check (labelled).** The first
  `tools/check-all.sh` run printed `overall: PASS` while pytest reported
  `1 failed, 731 passed`: `test_core_cli.py::test_environment_records_quartical_absence_or_presence`
  fails once `rangtoy._core` has been imported earlier in the session,
  because task H's `core_cli._rangtoy_modules` reads every imported
  `rangtoy*` module's `__file__` as UTF-8 text to count QuartiCal
  references, and the extension is a binary (`UnicodeDecodeError`). Two
  implementation changes, no criterion changed: `core_cli._rangtoy_modules`
  counts references in `.py` files only and records a binary module with
  `"binary": true` (and `environment()` now also records
  `rang_core_backend` and `rang_core_library`); and check-all's pytest step
  runs with `set -o pipefail` inside its sub-shell, because `… | tail -2`
  had been returning `tail`'s status, so a failing test had never failed
  the step. The three targeted modules (27 tests, with `_core` imported
  first) pass, and check-all was run a second time on the final code (the
  timing table); the plan's "full suite once" rule was broken knowingly,
  on an otherwise idle host, because the first run's PASS was false.

## Measured result (2026-10-29)

Extension built by `maturin develop --release --offline` with
`RUSTUP_TOOLCHAIN=1.93` (SHA256 `a11c8634…`, recorded as
`core_library_sha256` in the task C and I results of the run below).

**Criterion 1, build and install: pass.** `uv pip install --index-url
https://pypi.org/simple -e '.[pointing,beam,test,imaging]'` with the
maturin backend took 4.3 s with a warm cargo target directory (maturin and
its build dependencies from public PyPI, crates from crates.io, no vendored
crate); `import rangtoy._core` lists the seventeen functions and
`MsTable`. `tools/check-all.sh` with the three new steps, all offline: see
the timing table (overall PASS; `ext-build` 0.5 s warm).

**Criterion 2, C ABI kept: pass.** `core/src` unchanged; `cargo +1.93 build
--offline --release` of `core/` still exports the 22 `rang_core_*` symbols
(`outputs/core-j-20261029-03-compare/symbols-cdylib.txt`), and the ctypes
suite after the change is the precondition run itself, since every wrapper
reaches the same `library()` handle when `RANG_CORE_BACKEND=ctypes` (the
38 core tests pass under `RANG_CORE_BACKEND=ctypes` in 1.4 s and under
`extension` in 1.6 s).

**Criteria 3–5, policy, zero copy, unit-level identity: pass.**
`tests/test_core_backends.py`, 11 tests, 0.35 s: every wrapper function
(`fused_pass` with stored and scalar models, `solve_complex`,
`predict_components`, `blosc_decode`, `blosc_decode_rows`,
`core_zarr.read_rows`, `header_fields`, `read_chunk`, `stokes_i`,
`imaging_weights` in all three modes, `padded_size`, `grid_shape`,
`core_grid.invert` and `kernel`, `core_flag.flag_rows`, `core_ms.Table` on
the fixture ANTENNA table) is byte-identical under both backends; the same
exception class and message arise for a bad blosc chunk, a zero super
weight, a missing table and a singular solve; `_core.data_address` equals
`array.ctypes.data` for all eight dtypes and for row slices, a strided view
and a read-only output are refused with `TypeError`, and `grid_kernel`
fills a caller-owned array in place and refuses a wrong length; and the
three policy rules hold (ctypes forced never imports the extension,
extension forced never calls `library()`, `RANG_CORE_LIB` wins over the
implicit extension, auto picks the extension, a bad value raises).

**Criterion 6, archive bit identity: pass.** `RANG_CORE_BACKEND=extension
bash tools/core-j-suite.sh outputs/core-j-20261029-02-extension`:

| Step | Wall | Peak RSS | Outcome through the extension |
| --- | ---: | ---: | --- |
| phase 2 validator | 2.3 s | 119 MB | all 11 checks pass (cost 0.51 s, 97 MB) |
| section 6 prototype + checker | 7.4 s + 11.9 s | 144 MB, 437 MB | criteria 1–7 and 9–11 pass; criterion 8 **fails for the precondition's reason**: 2.46 s excluding decode (cold page cache; solve 0.35 s, fused 0.08 s, TV 0.07 s, survey 0.74 s, as in the precondition); labelled warm repeat `section6-warm` (4.5 s): all eleven pass, 1.46 s excluding decode, 144 MB |
| actions + comparator | 5.1 s + 0.02 s | 241 MB | 0 failures: 61 exact, 102 floats (6.6e-15), 24 differences (1.8e-11); inputs and `git status` unchanged |
| B comparator | 1.0 s | 84 MB | criteria 1–5 pass; weights identical, sums 1.8e-15 |
| C run + pixel comparator | 52.6 s + 0.3 s | 136 MB | criteria 1–3 pass; dirty 6.1e-7, PSF 4.2e-7 of peak, WCS equal |
| D run + comparator | 8.9 s + 0.4 s | 99 MB | criteria 1–5 pass |
| E checker | 0.6 s | 173 MB | criteria 1–3 pass, 0 failures on 173 columns |
| I replay (both comparisons) | 54.1 s | 213 MB | 0 failures against the archive and the host reproduction; inputs and `git status` unchanged |

Every number equals the precondition's. File by file
(`examples/compare_core_backends.py outputs/core-j-20261029-00-ctypes
outputs/core-j-20261029-02-extension … i-rerun`, receipt
`outputs/core-j-20261029-03-compare/compare-backends.json`, 0.5 s): 94
files, 4,544 JSON leaves, 60 `.npz` arrays and 60 FITS HDUs equal, zero
differences, zero files missing. The leaves skipped as volatile are counted
in the receipt: 2,093 per-read `timings` of the E checker, 186 `seconds`,
57 `code_sha256` (the wrappers changed between the two runs by
construction), 7 `cost`, 5 `module_sha256`, 3 `library_sha256` and 3
`core_library_sha256`, 4 run paths, and the rest wall times, RSS and
interpreter fields. The repeated task I run of the precondition
(`i-rerun`) against the extension's `i` is also identical (34 files, 1,784
leaves, 30 HDUs), as are the two warm section 6 repeats (3 files, 128
leaves, 2 arrays, `compare-section6-warm.json`).

**Criterion 7, side effects: pass.** The drivers' audits report inputs and
`git status` unchanged for actions and task I (the suite ran with the tree
untouched); the suite wrote only into `outputs/core-j-20261029-02-extension`,
and `maturin develop` wrote `python/rangtoy/_core.abi3.so` (ignored) and the
venv's `rangtoy.pth` and dist-info.

**Criterion 8, cost (reported).** Cold extension build (`core/py/target`
removed, `maturin develop --release --offline`): 7.5 s; warm: 0.46 s; the
first `cargo build` of the crate also took 7.4 s. Wheel
(`maturin build --release`, 0.14 s): `rangtoy-0.1.0-cp310-abi3-manylinux_2_35_x86_64.whl`,
800 KB (the `.so` is 1.3 MB; the tag is maturin's glibc detection, not an
auditwheel-checked manylinux wheel). In a fresh process
(`outputs/core-j-20261029-01-scratch/bench_boundary.py`, two repeats each,
load 0.5–0.8):

| | extension | ctypes |
| --- | ---: | ---: |
| `import rangtoy.core` (after NumPy, 0.036 s) | 8 ms | 8 ms |
| backend choice + first `fused_pass` (24 × 6 cells) | < 1 ms | 28–32 ms (`cargo build --offline` no-op check, `cargo metadata`, `CDLL`) |
| whole process (`/usr/bin/time`) | 0.14–0.15 s, 41 MB | 0.17 s, 40 MB |
| `fused_pass` 24 × 6 cells, per call over 1000 | 59.5–59.9 µs | 53.1–53.8 µs |
| `padded_size` scalar call, per call over 1000 | 0.12–0.15 µs | 0.53–0.54 µs |
| `fused_pass` 24 × 64 cells, per call over 100 | 232–250 µs | 233–236 µs |

The per-call boundary cost is in the noise for every real call (the
smallest kernel calls in the drivers are hundreds of times larger than the
24 × 6 case), but on that tiny case the extension is 6 µs slower than
ctypes: the `numpy` crate registers a shared or exclusive borrow for each
of the 22 arrays per call, and the wrappers add a `.view()` per complex
array. Scalar calls are four times faster. The first-call saving of about
30 ms per process is the only measurable gain; the point of the extension
is packaging (one `pip install`, no Cargo at import time, no `cargo
metadata` subprocess) and a typed boundary, not speed.

## Timings

| Date | Step | Wall | Peak RSS | Notes |
| --- | --- | --- | --- | --- |
| 2026-10-29 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 3.9 s | – | uv cache warm; numpy 2.5.4, maturin 1.16.0 |
| 2026-10-29 | `cargo +1.93 build --release` core and root crates, `CARGO_BUILD_JOBS=8` | 2.6 s + 1.0 s | – | before any task J code |
| 2026-10-29 | `cargo +1.93 fetch` of the `core/py` skeleton (pyo3 0.30.1, numpy 0.30.0 and 22 dependencies) | 3.3 s | – | the only network use of the crate build |
| 2026-10-29 | precondition suite on ctypes, `tools/core-j-suite.sh outputs/core-j-20261029-00-ctypes` (the table above) | about 150 s | 637 MB (checker) | load 0.7–2.9; section 6 cold-cache cost failure, warm repeat 4.5 s + 18.2 s; task I repeat 52.7 s |
| 2026-10-29 | first `cargo +1.93 build --offline --release` of `core/py` (cold, after the freeze) | 7.5 s | – | compiled first time; clippy and fmt clean after one type alias |
| 2026-10-29 | `uv pip install -e '.[pointing,beam,test,imaging]'` through the maturin backend (public PyPI, crates.io) | 4.3 s | – | warm cargo target; writes `python/rangtoy/_core.abi3.so` and `rangtoy.pth` |
| 2026-10-29 | `pytest` of the eight core test modules (38 tests) under `RANG_CORE_BACKEND=extension` and `=ctypes` | 1.6 s, 1.4 s | – | all pass on both |
| 2026-10-29 | `pytest tests/test_core_backends.py` (11 tests), several times while writing | 0.35 s | – | one abort found on the way: `rang_core_grid_kernel(7, 2)` panics with no `catch_unwind` (either backend); the test now uses WSClean's settings |
| 2026-10-29 | `maturin develop --release --offline` warm | 0.46 s | – | the `ext-build` step of check-all |
| 2026-10-29 | extension suite, `RANG_CORE_BACKEND=extension tools/core-j-suite.sh outputs/core-j-20261029-02-extension` (the table above) | about 145 s | 437 MB (checker) | load about 1; section 6 cold-cache cost failure as in the precondition; warm repeat 4.5 s + 11.7 s |
| 2026-10-29 | `examples/compare_core_backends.py` ctypes versus extension (three comparisons) | 0.5 s each | – | 94 + 34 + 3 files, zero differences |
| 2026-10-29 | `bench_boundary.py` under each backend, two repeats | 0.14–0.17 s per process | 40 MB | the cost table above |
| 2026-10-29 | `maturin develop --release --offline` cold (`core/py/target` removed) and `maturin build --release` wheel | 7.45 s, 0.14 s | – | wheel 800 KB |
| 2026-10-29 | `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8`, first run | 245 s (user 3,085 s) | 1.78 GB | every step PASS and `overall: PASS`, but pytest `1 failed, 731 passed in 234 s` (the `core_cli` environment test, masked by the pipeline; see the post-hoc note) |
| 2026-10-29 | `pytest tests/test_core.py tests/test_core_cli.py tests/test_core_backends.py` after the fix | 0.5 s | – | 27 passed, `_core` imported first |
| 2026-10-29 | `bash tools/check-all.sh`, second run on the final code | 80 s (user 574 s) | 1.71 GB | overall PASS: root 19 and core 47 Rust tests, clippy, fmt, `ext-build` 0.5 s, `ext-clippy`, `ext-fmt`, ruff, 732 pytest passed in 73 s; host idle |

## For the coordinator

Shared files this task did not edit, and what they need:

- **README.md.** The Python environment now needs Rust at `pip install`
  time: `pip install -e .` (or `uv pip install -e .`) builds
  `rangtoy._core` through maturin with the `cargo` on `PATH` (Rust 1.93 as
  for the checks; `RUSTUP_TOOLCHAIN=1.93` pins it when a newer default is
  installed). `python3 -m venv` still fails on this host (no `ensurepip`
  for Python 3.14); `uv venv -p /usr/bin/python3.14 .venv` then `uv pip
  install --python .venv/bin/python --index-url https://pypi.org/simple -e
  '.[pointing,beam,test,imaging]' ruff maturin` is what every wave used.
  Document `RANG_CORE_BACKEND` (`extension`, `ctypes`), that `RANG_CORE_LIB`
  selects ctypes on that library, and that without the extension the old
  import-time Cargo build still works. The Stimela recipes' 3.13 venv gets
  the same `abi3` extension from the same `pip install -e .`.
- **CONTRIBUTING.md.** Add the three check steps between the core crate and
  ruff: `.venv/bin/maturin develop --release --offline`, `cargo clippy
  --offline --all-targets --manifest-path core/py/Cargo.toml -- -D
  warnings`, `cargo fmt --check --manifest-path core/py/Cargo.toml`; note
  that the crate has no `cargo test` (an `extension-module` cdylib cannot
  link a test binary) and is tested from Python
  (`tests/test_core_backends.py`). The install line there
  (`pip --isolated install … -e '.[pointing,beam,test]' ruff`) now needs
  `cargo` on `PATH`.
- **STATE.md and README's research index.** Task J: implemented; measured;
  criteria 1–7 pass as frozen; this file. Next: task K once the licence
  answer is in; the container update of the feasibility study's row is not
  done here (no container was built or changed).
- **tool-timings.md.** The rows of the timing table above.
- **Containers and recipes.** Nothing changed; `recipes/core-*.yaml` do
  not set `RANG_CORE_LIB`, so they pick the extension when the venv has it
  and ctypes otherwise. If a container image is rebuilt, `pip install -e .`
  inside it now needs Rust and the crates.io fetch (or a vendored
  `cargo vendor` directory and `--offline`).
- **`core/src/ffi_grid.rs`, `core/src/ffi_weights.rs`** (observation, no
  edit made): `rang_core_grid_kernel`, `rang_core_weight_grid_shape` and
  `rang_core_padded_size` are the only C functions without `catch_unwind`;
  a panic in them aborts the process on either backend (`grid_kernel(7, 2)`
  does). Wrapping them is a one-line change each if wanted.
- **`python/rangtoy/core_cli.py`** (task H's; edited post-hoc, see the
  implementation notes): `_rangtoy_modules` no longer reads binary modules
  as text, and `environment()` records `rang_core_backend` and
  `rang_core_library`. Recipe receipts written from now on carry these two
  extra keys; task H's comparators do not compare the environment record.
- **`tools/check-all.sh`.** Besides the three `ext-*` steps, the pytest
  step now fails when a test fails (it never had before). The `root-test`
  and `core-test` steps still pipe `cargo test` through `grep | head -1`
  without pipefail and so cannot fail on a failing Rust test either; left
  alone here because `head -1` closing the pipe would make pipefail report
  a spurious SIGPIPE; `cargo test … > log; grep "^test result" log` would
  fix it.
- **Merge order.** This branch touches `pyproject.toml`, `.gitignore`,
  `tools/check-all.sh`, `core_cli.py` and six wrappers; nothing else is in
  flight.

## Open questions

- Should the extension release the GIL during kernel calls, as ctypes does?
  It would need `Send` wrappers around the borrowed pointers
  (`py.detach`); no present driver calls the core from threads, and the
  flagging campaign modules use the root crate's library, not the core.
- The 6 µs per-call overhead of the `numpy` crate's borrow registry on the
  tiny case is irrelevant today; if a future driver makes millions of small
  calls, passing the arrays once as a struct (`#[pyclass]` holding the
  views) would remove it.
- `maturin`'s wheel tag is `manylinux_2_35` from the host's glibc; a
  distributable wheel would need `auditwheel` or maturin's
  `--compatibility` with a manylinux container, which is the "CI, container
  update" half of the feasibility study's row and is not done here.
