# Big plan task P7: one entry door, no cargo at run time

Protocol frozen 2026-10-30 on branch `p7-architecture` (from main
`5965d37`) before any code was changed. Task P7 of [big-plan.md](big-plan.md),
section 3 "P7 Architecture" and section 4 row P7 of
[simplification-review.md](simplification-review.md), with the portability
items that [x1-crossplatform.md](x1-crossplatform.md) assigned to P7 and the
leftovers named by [wheel.md](wheel.md) ("Can the ctypes fallback be
dropped"), [p3-sumthreshold.md](p3-sumthreshold.md) (serial pack/unpack) and
[p5-memory.md](p5-memory.md) (flag copy, standalone P5 library).

Status: **protocol** (this section). Results follow in later sections.

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
