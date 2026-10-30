# Big plan task P7: one entry door, no cargo at run time

Protocol frozen 2026-10-30 on branch `p7-architecture` (from main
`5965d37`) before any code was changed. Task P7 of [big-plan.md](big-plan.md),
section 3 "P7 Architecture" and section 4 row P7 of
[simplification-review.md](simplification-review.md), with the portability
items that [x1-crossplatform.md](x1-crossplatform.md) assigned to P7 and the
leftovers named by [wheel.md](wheel.md) ("Can the ctypes fallback be
dropped"), [p3-sumthreshold.md](p3-sumthreshold.md) (serial pack/unpack) and
[p5-memory.md](p5-memory.md) (flag copy, standalone P5 library).

Status: **implemented and measured** (sections 4–6). The done criterion
passes: with no cargo on PATH, a wheel built by `tools/wheel/build.py` runs
every archived comparator and validator with its archived verdict, and its
outputs equal a pre-P7 run file by file (58 arrays and 60 FITS HDUs
byte-equal, no JSON number differing; the remaining differences are run
paths, code/library hashes and a load-dependent cost check). The golden
backend archive, the root kernels and the pointing toy are bit-identical on
Linux x86_64. The GIL is released (two concurrent predictor calls 2.02/1.60×
→ 0.92/1.12× one call), `rang_core_grid_kernel(7, 2)` returns 2 instead of
aborting, the Tricolour pack/unpack overhead fell from 24–32 ms to 4.5–5 ms
at 16 threads with identical flags, and native Windows passes the suite
(622 passed, 43 skipped with reasons, 0 failed). New finding: on Windows
MSVC the libm-based kernels (predictor, gridder, gain TV, projector, toy)
differ from Linux in the last bits (≤ 2.6e-15 relative), so X1's
bit-equality across platforms does not extend beyond the Tricolour port.

This is an engineering task under AGENTS.md, not a scientific
contribution: every archived number must stay bit-identical, and the gain
is a wheel-only install that runs the whole chain, no compiler at run time,
threads that overlap, and no process abort on a kernel panic.

## 1. Inventory at `5965d37`

### 1.1 The two Rust libraries and how Python reaches them

| Library | Built by | Reached from Python through |
| --- | --- | --- |
| `core/` (`rang_core`, rlib + cdylib) | maturin into `rangtoy._core` (the extension, `core/py`), or `core.build_core()` (`cargo build` of `core/`) | the extension; or ctypes on `librang_core.so` when `RANG_CORE_BACKEND=ctypes`, `RANG_CORE_LIB` is set, or the extension is missing |
| root crate `rang-toy` (`src/`, rlib + cdylib + bin) | `rangtoy.build()` (`cargo build` + `cargo metadata` of the root, on first use in every process) | ctypes on `librang_toy.so` through `projector._native_library()` (or `RANG_TOY_LIB`); the binary `rang-toy` through `subprocess` |
| P5 standalone (`core/target/p5-standalone`) | `core_fetch.build_p5_standalone()` (`cargo build`) | ctypes, only when neither the extension nor the core library exports the P5 symbols (dead since P5 merged into `core/src/lib.rs`) |

`core/` already depends on the root crate (`rang-toy = { path = ".." }`)
but does not use it, so the extension does not link it: `nm -D` of
`_core.abi3.so` shows the 24 `rang_core_*` symbols and none of the root's.

### 1.2 ctypes entry points of `core/` (the "ctypes branch", to delete)

| Python | C functions | Lines of ctypes plumbing |
| --- | --- | --- |
| `core.py` | `rang_core_fused`, `_solve_complex`, `_predict_components`, `_blosc_size`, `_blosc_decode`, `_blosc_decode_rows`; `build_core`, `library`, `RANG_CORE_LIB`, `RANG_CORE_BACKEND` | structs `_Inputs`, `_Outputs`, `_SolveInputs`, `_SolveOutputs`, `_PredictInputs`, `_PredictOutputs` |
| `core_grid.py` | `rang_core_grid_invert`, `_grid_kernel` | `_GridInputs`, `_GridOutputs`, `_lib` |
| `core_weights.py` | `rang_core_weight_grid_shape`, `_padded_size`, `_stokes_i`, `_imaging_weights` | four structs, `_lib` |
| `core_flag.py` | `rang_core_flag_rows` | `_FlagInputs`, `_FlagOutputs`, `_lib` |
| `core_zarr.py` | `rang_core_blosc_header`, `_decode_block`, `_decode_span_rows` | `_lib` |
| `core_ms.py` | `rang_core_ms_open`, `_close`, `_describe`, `_read`, `_free`, `_last_error` | `_Column`, `_lib` |
| `core_fetch.py` | `rang_core_correct_stokes_i`, `_blosc_decode_span_rows_strided` | `CorrectInputs`, `p5_library`, `build_p5_standalone`, `RANG_P5_LIB` |
| `core_campaign_array.py:998` | `rang_core_correct_stokes_i` (the else branch of `correct_stokes_i`) | uses `core_fetch.p5_library` |

Other users of the ctypes path or of `RANG_CORE_LIB`:
`examples/prototype_section6.py:253` (`core.library()` unconditionally),
`examples/bench_core_f.py:183` (`rang_core_blosc_decode` directly),
`examples/validate_core_phase2.py` (the cost subprocess names the library
through `RANG_CORE_LIB`), `examples/bench_p1_solver.py`,
`examples/bench_p2_gridder.py`, `examples/bench_p3_flags.py`,
`examples/bench_p5_memory.py` (A/B benches of two libraries),
`tests/test_core_backends.py` (ctypes as the oracle), `tools/core-j-suite.sh`,
`tools/wheel/{build.py,build-inside.sh,test.py,test.sh,smoke.py,run_installed.py,pytest_wheel.py}`
and `.github/workflows/wheels.yml` (a `ctypes/` library beside the wheel for
the backend tests).

### 1.3 Root-crate kernels and their callers

| C function (`src/`) | Rust function | Python callers |
| --- | --- | --- |
| `rang_gain_tv` (`tv.rs`) | `tv::edges` | `flagging.gain_tv` (frozen) → `core_campaign`, `core_campaign_array`, `core_campaign_1830`, `core_trend`, `core_signal`, `core_actions`, notebooks 01/03/05 |
| `rang_trend_slopes` (`trend.rs`) | `trend::slopes` | `flagging_trend._kernel` (frozen, hash-checked) |
| `rang_response_jacobian`, `_normals`, `_step` (`response.rs`, P4 QL eigensolver in `linalg.rs`) | `response::{jacobian, normals, anchored_step}` | `flagging_influence._functions` (frozen) → `flagging_response`, `flagging_equivariance`, …; `examples/bench_p4_eigen.py`, `tests/test_p4_eigen.py` (ctypes on `_native_library()._name`) |
| `rang_project_out` (`projector.rs`) | `projector::project_out` | `projector.project_out` |
| binary `rang-toy` (`main.rs`, `lib.rs::run`, `pointing_*reference_json`) | — | `rangtoy.run_experiment`, `tests/conftest.py` (pointing fixtures), `tests/test_toy.py`, 13 pointing examples (`subprocess.check_output([build(), "--pointing-reference"])`) |

`_native_library()._name` (the library path) is also hashed into receipts
by the frozen `flagging_equivariance`, `flagging_influence`,
`flagging_next`, `flagging_prospective`, `flagging_signal_guard` and
`flagging_trend` (none passes it to a child process).

The frozen modules call the kernels positionally with NumPy arrays and
Python ints after setting `.argtypes`/`.restype`; none passes a ctypes
scalar or `byref`. `projector.project_out` passes `ctypes.byref(rank)`.

### 1.4 C functions without `catch_unwind`

Six of 24 in `core/src/ffi*.rs`: `rang_core_grid_kernel` (aborts the
process for `(7, 2)`, task J), `rang_core_weight_grid_shape`,
`rang_core_padded_size`, `rang_core_ms_last_error`, `rang_core_ms_close`,
`rang_core_ms_free`. The six root-crate functions all have it.

### 1.5 GIL

No extension function releases the GIL. Before (this host, extension,
`RAYON_NUM_THREADS=1` so the solver's rayon pool cannot hide the effect,
`core.solve_complex` on 12 stations × 60 times × 64 channels, 7 iterations):
one call 0.082 s, two threads concurrently 0.174 s, **ratio 2.12**
(`outputs/p7-architecture-20261030-01/before/gil-before.json`).

### 1.6 First-call cost before

Measured here, load from sibling tasks present: the first `flagging.gain_tv`
in a process with a cold root target runs `cargo build` (4.17 s compile;
4.55 s first call including import; D2 measured 33.6 s with a cold registry
and a loaded host, [d2-notebook.md](d2-notebook.md)); with a warm target
every process still runs `cargo build` and `cargo metadata` (first call
0.081–0.100 s including the import). `import rangtoy.core_campaign` takes
0.072–0.123 s (`-X importtime` 77 ms cumulative). Receipts:
`outputs/p7-architecture-20261030-01/before/`.

## 2. Design

1. **Root kernels into the extension.** `core/py` calls the six root-crate
   C functions (`rang_toy::tv::rang_gain_tv`, …) exactly as it calls the
   core's: NumPy buffers borrowed in place, the C status returned. The root
   crate stays where it is as an rlib (its unit tests unchanged); its
   `cdylib` crate type is dropped, so `librang_toy.so` is no longer built.
   The pointing toy's command line moves into `rang_toy::cli(args) -> String`,
   called by both `main.rs` and an extension function, so its output is
   byte-identical to the binary's stdout.
2. **`projector._native_library()` keeps its name and shape** for the frozen
   modules (they cannot change): it returns an object whose attributes
   `rang_gain_tv`, `rang_trend_slopes`, `rang_response_*`, `rang_project_out`
   accept `.argtypes`/`.restype` assignments (ignored) and forward the
   positional call to the extension, and whose `_name` is the extension's
   file (so receipts hash the binary that ran). `RANG_TOY_LIB` and
   `rangtoy.build()` are removed.
3. **Python wrappers** call the extension only. `core.backend_name()`
   returns `"extension"`, `core.extension()` the module, `core.library_path()`
   its file (names kept for receipts, smoke tests, P9 and P12).
   `RANG_CORE_BACKEND` and `RANG_CORE_LIB` are documented no-ops that raise
   if they ask for the ctypes backend, so an old command line cannot silently
   claim a library it did not use.
4. **GIL** released (`py.detach`) around every kernel call of `core/py`.
5. **`catch_unwind`** on the six C functions of 1.4; a panic returns the
   function's "panic" status (2 where the function has a status, 0 for the
   two `usize` returns, nothing for the two `void` ones).
6. **Portability (X1 → P7)**: `peak_rss_bytes()` helper (`resource` lazily,
   macOS bytes vs Linux KiB, `psutil` or Windows API otherwise) replacing
   the module-level `import resource` in `core_campaign.py` and
   `core_campaign_array.py`; a `symlink_or_skip` fixture in
   `tests/conftest.py`; `st_blocks` and the POSIX `tricolour` path are in
   frozen modules, so their tests are skipped on Windows with a reason;
   `as_posix()` in the receipt tree hashes of the non-frozen examples
   (identical strings on POSIX, so archived Linux hashes do not move); the
   `→` print in `examples/pointing.py:167`; the `ZipInfo("a\\b")` test.
7. **Pack/unpack of `ffi_flag.rs`** parallel over rows with rayon.
8. **`core.solve_complex`** passes bool or uint8 flags (C-contiguous) to the
   kernel without a copy: the solver reads `flag != 0`, the same predicate
   as `np.asarray(flag, bool)`.
9. `tools/check-all.sh`, the wheel tools, `CONTRIBUTING.md` and the README
   install text lose the ctypes and cargo-at-import steps.

## 3. Acceptance (frozen)

**Done criterion.** With **no cargo on PATH**, after `pip install` of a
wheel built by `tools/wheel/build.py --no-ctypes` into a fresh venv, every
archived comparator and validator passes bit-identically, as archived:
`validate_core_phase1.py`, `validate_core_phase2.py` (including `--cost`),
`prototype_section6.py` + `check_section6.py`, the `compare_core_*.py`
comparators of the core-j suite (phase 2, section 6, actions, B, C, D, E, I)
plus `compare_core_trend.py` and `compare_core_signal.py` where their
archives are present, `bench_core_f.py check`, the K precondition
(`precondition_luno_campaign.py` against `results/core-k-luno-campaign.json`),
and D2's notebook execution tests.

Gated criteria:

1. **`tests/test_core_backends.py` becomes extension against archive.**
   Before any code changes, each of its cases (and new cases for the six
   root kernels and the pointing toy) runs under both backends at
   `5965d37`; they must be byte-identical (as task J found), and the outputs
   are written to `tests/data/core-backends-golden.npz` with their SHA-256
   values, committed on their own. Afterwards the test compares the
   extension to that archive: byte-identical on x86_64; on other
   architectures (no archive was made there) within 4 ulp relative, labelled.
2. **`import rangtoy` and every kernel call run no cargo**: a test with
   `cargo` removed from `PATH` (and a poisoned `cargo` first on PATH that
   fails) imports every module of `rangtoy` and calls every root kernel.
3. **GIL released**: the two-thread run of 1.5 at `RAYON_NUM_THREADS=1`
   finishes in about one call's time (ratio ≤ 1.3), and a pytest checks
   that a second thread makes progress while a kernel runs.
4. **No abort on panic**: `rang_core_grid_kernel(7, 2)` through the
   extension returns status 2 (it aborted the process before), in a test.
5. **Windows**: in a clone of this branch on native Windows, every failure
   of X1's table is fixed or skipped with a reason, and the suite has no
   other failure.
6. **Pack/unpack parallel, flags bit-identical**: task D's comparator
   (`compare_core_flags.py`) passes; the P3 bench reports the before/after
   time of the pack/unpack share.
7. **Flag copy removed, bit-identical**: phase 2 validator passes; a test
   checks that a bool and a uint8 flag cube reach the kernel at their own
   address (no copy) and give the same gains.
8. **Pointing toy output byte-identical**: `--pointing-reference`,
   `--pointing-full-reference`, the default run and two `run_experiment`
   settings equal the binary's stdout captured at `5965d37`
   (`before/toy-*.json`) except the timing-free fields that name the binary.
9. **Timings before/after**: the first-call cost (cargo build → 0) and the
   import time of the K chain (`import rangtoy.core_campaign` plus the first
   `gain_tv`).
10. `bash tools/check-all.sh` passes once before the final commit.

Not gated: kernel speed (no kernel changes except pack/unpack).

## 4. What changed (implemented)

Commits on `p7-architecture`: `ac94024` protocol, `12958cb` golden archive
(before any code), `86fd7c8` implementation, `5aebbed` merge of main
`7b690eb` (L5), `67c754e` L5 adaptation, `b3ef259` Windows tolerance,
`f7c97ab` static masks as package data, `8ba922c` POSIX receipt paths, then
this report.

- **Rust.** The root crate is an rlib only (no `librang_toy`); `main.rs`
  calls the new `rang_toy::cli`, shared with the extension. `core/src/lib.rs`
  re-exports it as `rang_core::toy`, so the extension links it (its `.so`
  now also exports the six root C symbols, so `ctypes.CDLL(_core.__file__)`
  still serves A/B benches such as `bench_p4_eigen.py`). `core/py/src/lib.rs`
  binds `gain_tv`, `trend_slopes`, `response_{jacobian,normals,step}`,
  `project_out` (with length checks ctypes could not do) and `toy_cli`, and
  runs every kernel under `py.detach` (a `Detached` wrapper makes the
  pointer-holding closure `Send`; the job stays on the calling thread).
  `catch_unwind` added to `rang_core_grid_kernel`, `_weight_grid_shape`,
  `_padded_size` (0 on panic), `_ms_last_error` (0), `_ms_close`, `_ms_free`.
  `ffi_flag.rs` packs by finding each (baseline, time) slot's last row
  serially, then filling slots in parallel; unpack is parallel over rows.
  `solve.rs` untouched (L5's edits merged as they are).
- **Python.** `core.py`, `core_grid.py`, `core_weights.py`, `core_flag.py`,
  `core_zarr.py`, `core_ms.py`, `core_fetch.py` lost every ctypes struct,
  `_lib`, `build_core`, `p5_library`, `build_p5_standalone`, `CorrectInputs`
  (about 560 lines). `core.backend_name()` is always "extension",
  `core.library()` returns the extension (drivers call it "to load before
  timing"), `library_path()` its file; `RANG_CORE_BACKEND≠extension` or a set
  `RANG_CORE_LIB` raise a `ValueError` naming this report. `rangtoy.build()`
  and `RANG_TOY_LIB` are gone; `rangtoy.toy_output(*args)` and
  `run_experiment()` run the toy in the extension (`binary=`/`RANG_TOY_BIN`
  still run a binary). `projector._native_library()` returns a shim whose
  kernel attributes accept `.argtypes`/`.restype` and forward positional
  calls to the extension, `_name` being the extension file: the frozen
  `flagging*.py` modules are unchanged and their receipts hash the binary
  that ran. `core.solve_complex` passes bool/uint8 flags without a copy
  (`_flags`, nonzero = flagged as before). New `rusage.py`
  (`peak_rss_bytes`, `peak_rss_mb`, `cpu_seconds`; macOS bytes vs Linux KiB;
  Windows `K32GetProcessMemoryInfo`) replaces the module-level `import
  resource` of `core_campaign.py`, `core_campaign_array.py` (only those
  lines; its now-dead P5 ctypes branch was left as is) and L5's
  `core_solver_study.py`. The Tricolour static masks moved from `core/data/`
  to `python/rangtoy/data/` (package data, with README and licence) so the
  wheel needs no checkout for the flagging chain and notebooks.
- **Examples.** 13 pointing examples call `toy_output` (byte-identical to the
  binary's stdout); `bench_core_f.py` calls the extension's exported C symbol
  through ctypes (same timed call); `validate_core_phase2.py`'s cost
  subprocess no longer sets `RANG_CORE_LIB`; `prototype_section6.py` loads
  `core.extension()`; `pointing.py:167` prints `->`; 14 receipt hash sites
  use `relative_to(...).as_posix()` (identical strings on POSIX); the P4
  bench's load average is optional off Linux.
- **Tests.** `test_core_backends.py` is extension-against-archive
  (`tests/data/core-backends-golden.{npz,json}`, 41 arrays and 145 leaves
  recorded under both backends at 5965d37 and byte-equal there; the root
  kernels from `librang_toy` at 5965d37). New `test_p7_architecture.py`
  (poisoned `cargo` never run at import or kernel call, every module
  imports, ctypes requests refused, `grid_kernel(7, 2)` → 2 in a
  subprocess, a second thread runs during a solve, flags passed in place,
  the parallel pack keeps the last duplicate row). `test_toy.py` checks the
  five archived toy outputs byte for byte (`tests/data/toy-golden.json`).
  `conftest.py` has a `symlink` fixture (skip on WinError 1314); the frozen
  modules' `st_blocks` and POSIX-path tests are skipped on Windows;
  `ZipInfo` test fixed; `test_l5_solver.py` on one backend.
- **Tools and docs.** `build.py` builds no ctypes library (`--no-ctypes`
  accepted, no effect); `test.py`/`test.sh`/`pytest_wheel.py`/`wheels.yml`
  run the three test files above against the wheel with no C ABI library;
  `build-inside.sh` builds neither `librang_core.so` nor `librang_toy.so`;
  `run_installed.py` also points the frozen trend runner's source receipts
  at the checkout. `check-all.sh` unchanged (no ctypes step existed).
  README, CONTRIBUTING (native Windows status) and `examples/README.md`
  lose cargo-at-import.

## 5. Results

### Done criterion: wheel only, no cargo

Wheel `rangtoy-0.1.0-cp310-abi3-manylinux_2_35_x86_64.whl` (SHA256
`1204724f…`, 1,628,433 bytes) built at `f7c97ab` by `tools/wheel/build.py`
(32.7 s, RUSTFLAGS `-C target-cpu=x86-64`), installed with
`[test,imaging,notebook]` and numcodecs 0.17.1 into a fresh uv venv
(CPython 3.14). Every step ran under `env -i PATH=/usr/bin:/bin` (cargo
absent, asserted) through `tools/wheel/run_installed.py`. Before: the same
steps from a checkout of main `7b690eb` (no P7, dev build, cargo on PATH).

| Step | Wheel (`-06`, `-08` trend, `-05` F) | Before (`-03`, `-05` F) |
| --- | --- | --- |
| phase 1 validator | pass as archived, 1.1 s | pass, 6.3 s |
| phase 2 validator (incl. `--cost`) | all 12 pass, 1.2 s | pass |
| section 6 + checker | all 11 pass, 4.6 s | 10 of 11: criterion 8 cost failed under load (as known) |
| actions + comparator | pass (61 exact, 102 float ≤ 6.6e-15, 24 difference) | same |
| B weights | pass | pass |
| C gridder + comparator | pass (dirty ≤ 6.1e-7 of peak) | same |
| D Tricolour + comparator | pass | pass |
| E MS reader | pass | pass |
| I imaging replay (both comparators) | pass | pass |
| F `bench_core_f.py check --target all` | all checks pass, 37.3 s | all pass, 37.0 s |
| K precondition | all checks, χ² 0.26823507037914956 | same |
| trend (frozen runner) + comparator | pass: 875 exact, 168 float, 1 excluded | same |
| signal + comparator | pass: 261 exact, 208 float (≤ 1.74e-11), 4 difference | same |
| D2 notebooks (`test_notebook_execute.py`) | 6 passed | 6 passed |

Two wheel-side steps failed first and were fixed, not waived: the notebooks
and the flagging chain needed `core/data/` (fixed by shipping the masks,
`f7c97ab`), and the frozen trend runner hashes the source tree beside its
module (fixed in `run_installed.py`'s checkout shim; its kernels are the
wheel's). The `import` row of the scripts is a harness artefact
(`run_installed.py` takes a script, not `-c`); the import check passed in
`after/`. The CLI stub's exit status was corrected for the comparators
(`rang-core` itself exits 0).

**Bit identity against the pre-P7 run.** `compare_core_backends.py -03 -06`
(`outputs/p7-architecture-20261030-09`): 95 files, 4,519 JSON leaves, 58
arrays and 60 FITS HDUs; every array and HDU byte-equal, no number differs
(`classify_compare.py`: numbers above 1e-9: 0). The 28 listed differences:
21 run paths, 2 the section 6 cost check (failed in the loaded before run),
`head.txt`, two `comparator_sha256` (the imaging comparator module changed
by `as_posix`), signal's `acceptance_digest_core` (volatile, design
deviation 5 of P6), and `trend-compare.json` (the wheel trend ran in `-08`).
Trend: all seven checkpoints byte-equal; `config.json`/`result.json`
differ only in the runtime receipts (paths and the native library hash),
`seconds` and `native_library_sha256`.

### Gated criteria

1. **Golden archive**: generated at 5965d37 under ctypes and the extension,
   byte-equal (41 arrays, 145 leaves); the P7 extension reproduces it on
   Linux x86_64 (dev build and wheel).
2. **No cargo**: `test_p7_architecture.py` passes in the dev venv, the
   wheel venv and on Windows; every acceptance step above ran with cargo
   absent.
3. **GIL** (`outputs/p7-architecture-20261030-01/{before,after}/gil2-*.json`,
   interleaved, load about 9.9): two threads calling
   `predict_components` (serial kernel, 0.19–0.25 s per call) took
   2.02× and 1.60× one call before, 0.92× and 1.12× after. The solver is
   not a valid probe: concurrent solves queue on the shared rayon pool
   (2.12× before, 2.37× after at `RAYON_NUM_THREADS=1`), so the protocol's
   solver measurement was replaced by the predictor (deviation, recorded).
   `gain_tv` was already released before (ctypes drops the GIL): 1.21/1.29×
   → 1.38/1.08×.
4. **Panic**: `_core.grid_kernel(7, 2, out)` returns 2 (subprocess test);
   before, the process aborted.
5. **Windows** (`C:\Users\gijsm\Build\tmp\20261030-rang-p7`, head `b3ef259`,
   Rust 1.93 MSVC, CPython 3.14): 622 passed, 43 skipped, 0 failed (153 s).
   X1's failures: `resource` (3 modules) fixed; `st_blocks` (frozen
   `flagging_equivariance`, `flagging_imaging`, 10 tests) skipped with a
   reason; symlinks (4) skip through the fixture; the `tricolour` POSIX path
   (frozen `flagging_caracal`) skipped; `ZipInfo` fixed; `→` fixed. The
   toy's archived bytes are Linux-only (skipped with a reason), but the
   extension's toy output equals a Windows-built `rang-toy.exe` byte for byte
   in all five cases. Golden differences on Windows, all within the
   labelled tolerance: gridder ≤ 2.2e-16 of the peak (1,393 of 2,304
   pixels), gain TV ≤ 4e-16 relative, projector ≤ 2.6e-15, predictor one
   value at 1e-16; fused pass, solver, weights, Tricolour, trend and
   response byte-equal.
6. **Pack/unpack** (`outputs/p7-architecture-20261030-10`, task D's four
   controls, `bench_p3_flags.py run --per-step`, before = 7b690eb dev build,
   after = P7 dev build, both x86-64-v3, 3 rounds, load 6–10): flags and
   every per-step window hash identical in all 112 runs. Packing overhead
   (a `flag_autos` call) 24–32 ms → 4.5–5.2 ms at 16 threads, 24–29 ms →
   6.9–7.8 ms at 4. Sum of the four controls' best core seconds 0.69–0.72 s
   → 0.59 s at 16 threads, 1.21–1.30 s → 1.11 s at 4. (The wheel, built for
   baseline x86-64, is slower than either dev build, 0.93 s: P0's ISA
   effect, not P7.)
7. **Flag copy**: a test shows bool, uint8 and uint8-with-2 flags reach the
   kernel at their own address with identical gains; the phase 2 validator
   passes. Saved: one uint8 copy of the flag cube per solve (4 B per cell).
8. **Toy bytes**: all five archived outputs reproduced byte for byte on
   Linux x86_64 (`test_toy.py`).
9. **Timings** (`outputs/p7-architecture-20261030-01/firstcall.tsv`,
   interleaved, five repeats, load about 9.9): first `flagging.gain_tv` in a
   fresh process including imports 0.101–0.124 s before (warm target: a
   `cargo build` no-op and `cargo metadata` per process) → 0.073–0.087 s
   after (cargo absent); with a cold target before it was 4.55 s (4.17 s
   compile here; D2 measured 33.6 s on a cold registry) → no compile at all.
   `import rangtoy.core_campaign` unchanged: 0.090–0.142 s before,
   0.082–0.103 s after.
10. `bash tools/check-all.sh`: section 6.

## 6. For the coordinator

- **Timing rows** (for `research/tool-timings.md`): wheel build
  `tools/wheel/build.py` 32.7 s; wheel-only acceptance suite about 120 s of
  steps (F 32 s, signal 13 s, notebooks 18 s, trend 17 s); Windows clone
  7 s, editable install with the MSVC extension 64 s, `maturin develop`
  67 s, full pytest 153 s; golden generation (both backends) 19 s.
- **P9 (one CLI)**: `core.backend_name()`, `core.library()` and
  `core.library_path()` remain as compatibility names (always the
  extension); `core_cli` receipts record `rang_core_backend` and
  `rang_toy_lib` (now always None unless set by hand). The A/B sweeps of
  `bench_p1_solver.py` and `bench_p2_gridder.py` set `RANG_CORE_LIB`, which
  is now refused: A/B needs two venvs (or `ctypes.CDLL` of two extension
  files, which export the C ABI).
- **P12 (rename)**: the extension module, `toy_cli`, `python/rangtoy/data/`
  (package data) and the frozen-module shim in `projector.py` move with the
  package; `rangtoy.build` no longer exists.
- **History**: nothing retired to `history/`; the A/B benches above are
  candidates once P9 decides.
- **Upstream** (non-RATT): PyO3 0.30's `Python::detach` requires an `Ungil`
  (= `Send`) closure, so binding raw-pointer C ABIs needs an explicit
  wrapper; worth a PyO3 docs example. Rayon's global pool makes concurrent
  callers from Python threads queue, so GIL release alone does not overlap
  rayon kernels. No RATT/caracal-pipeline observation from this task.
- **Evidence**: `outputs/p7-architecture-20261030-01` (before/after
  timings, GIL, golden generation), `-02` (first wheel, prep), `-03`
  (before suite), `-05` (final wheel, F), `-06` (wheel suite), `-08`
  (wheel trend), `-09` (file-by-file comparison), `-10` (pack/unpack);
  Windows logs `C:\Users\gijsm\Build\tmp\20261030-rang-p7-logs` (copied to
  `-11`).
