# W4-2 and W4-7: boundary checks, and the GPU feature in the gate

Fix tasks W4-2 and W4-7 of the big plan's wave 4 ([w4-review.md](w4-review.md),
"Proposed fix tasks"), for review findings W4R-04, W4R-05, W4R-09 and W4R-10
(W4-2) and W4R-15 (W4-7). Branch `w4-2-boundaries` from `main` `ecccbf0`,
with `main` merged in three times (`fdf186b`, W4-3; `d03a95a`, W4-1 and W4-5; `9813608`, E6).

Status: **implemented and measured.** Both r01 cases and all three r06 cases
now raise `ValueError`. Every number the identity suite writes is
bit-identical to the unmodified `ecccbf0`: 282 arrays, 88 FITS HDUs and
22,500 JSON leaves. The only differences are run paths, timings and code
hashes, classified below. The decode identity of `tests/test_p5_memory.py`
passes. `rang-core check` now has 17 steps. The two new GPU steps add 6.1 min
to a cold check (48 s clippy, 315 s test) and 3 s to a warm one, so they can
be left out with `--skip core-clippy-gpu,core-test-gpu`.
`overall: PASS` on WSL and on native Windows: see "Checks".

## What changed, file by file

- **`core/py/src/lib.rs`** (coordinator file; the hunks are listed under "For
  the coordinator").
  - New helpers:
    - `c_slice` and `c_slice_mut` refuse an array that is not C-contiguous
      with `ValueError("<name> must be C-contiguous")`. rust-numpy's
      `as_slice` also accepts Fortran order, which a kernel then reads
      transposed.
    - `size(name, factors)` takes a `checked_mul` product and raises
      `ValueError("<name> overflows")`.
    - `arg`, `opt_arg`, `arg_mut` and `opt_arg_mut` check C order and the
      exact element count the C ABI documents, and raise
      `ValueError("<name> must hold N elements, not M")`.
  - `ptr`, `ptr_mut`, `sized`, `sized_mut` and `data_address` now go through
    `c_slice`/`c_slice_mut`. Every binding therefore refuses F-ordered
    multi-dimensional arrays, including the wgridder bindings, the P7
    root-kernel bindings and W4-3's `exact_input`/`exact_output`.
  - Named length checks were added to the bindings that had none: `fused`,
    `predict_components`, `stokes_i`, `imaging_weights` (the grid's length
    comes from `WeightGrid::shape` when `super_weight > 0`), `grid_invert`,
    `grid_invert_gpu` and `flag_rows`.
    - `flag_rows` checks `mask_offsets` (`nmasks + 1`), checks that
      `mask_freqs` equals its last offset, and checks `steps`,
      `intensity` and `stages`.
    - `solve_complex` gets one inserted block of checks. Its signature and
      its `SolveInputs` literal are untouched (W4-1).
  - `checked_mul` is also used in `blosc_decode_rows`,
    `blosc_decode_span_rows`, the wgridder's `nrow * nchan`, `nx * ny` and
    `2 * n`, and `correct_stokes_i` (`ntime_bins * nfreq_bins * nant`,
    `8 * cells`, `8 * gains`). `correct_stokes_i` and the P7 root-kernel
    bindings keep their status-1 convention for a length mismatch.
  - W4-3's `closure_scores` and `fluxstd_eval` were written with
    `exact_input`/`exact_output`: a standard-layout check plus an exact
    shape check. I verified them and left them unchanged. Their pointers now
    also pass through the C-checking `ptr`.
- **`core/py/src/clean.rs`** (not in the owner list; see "Deviations"). The
  certified-CLEAN binding's `as_slice` calls go through `c_slice`. It already
  checked its lengths.
- **`core/src/ffi_grid.rs`, `core/src/gpu/ffi.rs`**: `nrow * 3`,
  `nrow * nchan * 2` and `width * height` are `checked_mul`. An overflow
  returns status 1 (CPU) or an `Err` (GPU).
- **`core/src/blosc.rs`**: the new `check_rows_covered` requires rows that are
  non-decreasing and lie entirely inside the decoded bytes of blocks
  `first..first + count`, with every product checked. `decode_span_rows`
  calls it and checks its buffer product. Before this, an uncovered row was
  skipped and kept the caller's `np.empty` bytes, with status 0. A Rust unit
  test covers both.
- **`core/src/ffi_correct.rs`**: the strided span decoder calls
  `check_rows_covered` and returns 1 for an uncovered row.
- **`core/src/ffi_fluxstd.rs`**: `rang_core_fluxstd_eval` runs inside
  `catch_unwind` and returns 2 on a panic; before, a panic aborted the
  process. A grep over every `extern "C" fn` in `core/src` found these
  entries without their own `catch_unwind`:
  - the wgridder entries, which delegate to `run`, `run_ex` and
    `run_d2v_ex`, all three guarded;
  - `rang_core_wgridder_kernel_row` and the two `*_last_error` functions,
    which hold no panicking code beyond a `RefCell` borrow.

  Those last three are in files outside this task's owner list, so they are
  only recorded here.
- **`python/rang/core_flag.py`**: `flag_rows` refuses `antenna1`, `antenna2`
  or `times` without `nrow` entries, and `corr_type` without `ncorr`
  entries, with a `ValueError` naming the array.
- **`python/rang/core_zarr.py`**:
  - New `check_meta(meta, name, dtype)` refuses filters, object dtypes,
    compressors other than blosc, `order` other than `"C"`, big-endian
    dtypes, and a dtype other than the expected one. `array_meta` uses it
    and reads the file as UTF-8.
  - `block_table`, `blocks_in_order` and `whole_chunk_rows` now live here,
    so the local and the fetched paths share one copy. `read_rows` uses
    them.
  - New `check_rows_covered`, the Python form of the Rust check, which
    `decode_span_rows` now calls.
- **`python/rang/core_fetch.py`**:
  - `block_table` is `core_zarr.block_table`.
  - Blocks stored out of order now fall back to a full decode:
    - `read_rows_into` decodes the whole chunk and writes the rows at
      their strided offsets (`_write_rows`, bounds-checked);
    - `plan_runs` plans the whole chunk, `(0, nblocks, 0, cbytes)`;
    - `decode_slice` decodes that span in full.
  - `fetch_slice` runs `check_meta` on every fetched `.zarray`, including
    the row columns' expected dtypes. `decode_slice` reads tile metadata
    through `array_meta`. `decode_rows_into` calls `check_rows_covered`.
  - Found while testing: `fetch_slice` cached one HTTP client per thread for
    the whole process, so a second call in the same thread talked to the
    first call's base URL. It now keeps one client per thread and base URL.
- **`python/rang/check.py`** (W4-7): two new steps after `core-fmt`.
  - `core-clippy-gpu`: `cargo +1.93 clippy --offline --all-targets -q
    --manifest-path core/Cargo.toml --features gpu -- -D warnings`.
  - `core-test-gpu`: `cargo +1.93 test --offline --release -q
    --manifest-path core/Cargo.toml --features gpu`.

  The docstring now says 17 steps and names the `--skip` form.
- **`examples/run_luno_array.py`, `run_luno_1830.py`, `run_l1m.py`,
  `run_c1.py`** (not in the owner list; see "Deviations"): the `outputs/`
  prefix test uses `as_posix()`, and the `MemAvailable` print skips `None`
  (the first three scripts). Output on Linux is unchanged.
- **Tests:**
  - New `tests/test_w4_2_boundaries.py`: the r01 cases; named lengths and
    overflow; P7's status 1 kept, with F order now refused.
  - `tests/test_core_flag.py`: five short-array cases.
  - `tests/test_core_zarr.py`: an out-of-order chunk builder and fallback
    test; uncovered span rows, through the binding, the strided binding
    and the wrapper; five metadata refusals.
  - `tests/test_core_fetch.py`: the out-of-order fallback locally and over
    HTTP; a row column with the wrong dtype is refused.
  - `tests/test_core_cli.py`: the step list now has 17 entries, with the
    two GPU labels.

## Measured acceptance

| Criterion | Run | Result |
| --- | --- | --- |
| r01 (a) 1-element `split_stats` | `outputs/w4-2-20261031-01/a01_boundaries.log` (each case in its own `try`); the unmodified r01: `r01_ffi_bounds-unmodified.log` | **ValueError** `split_stats must hold 12 elements, not 1`; `big[1:12]` untouched; a 12-element buffer returns 0 |
| r01 (b) F-ordered `uvw` | same | **ValueError** `uvw must be C-contiguous` (C order: status 0, same visibilities as the review's C-order run); `data_address` of an F array: ValueError |
| A mismatched `flag_rows` raises | r06's three cases in `a01_boundaries.log` | **ValueError** for `antenna1/antenna2` short, `times` short and `corr_type[:1]`; the reference digest `bc3ef20a…` is unchanged |
| Backends comparator, and C, D, I, K, P5 identical | identity suite (P11's live chain, no coverage) on `ecccbf0` (unpacked in `~/Build/tmp`, own venv) and on this branch: `outputs/w4-2-20261031-02/{base,head}`, `rang-core backends compare base head` | **Numerically identical**: 282 arrays and 88 FITS HDUs byte-equal, 22,500 JSON leaves equal. The comparator's 572 failures are all non-numerical (`classified.json`): 27 strings naming the same file under the two checkout roots; 292 `runtime_receipts` entries keyed by root; 241 timing, load and memory leaves outside its VOLATILE set; 4 code or library hashes; 5 hashes over timings (`frozen_train_responses_sha256` includes `full_training_normals_seconds`, and `acceptance_digest_core` includes `metrics/seconds`; they also differ between P11's runs `-03` and `-04`); 3 phase files missing on the base only. Every step's status is the same on both sides. The C, D and I comparators against their archives pass (`c-compare`, `d-compare`, `i-compare`, `i-compare-host`). K: `campaign precondition` passes. P5: `campaign-array precondition` (P5 criterion 1) passes. `trend-compare` fails as frozen (known) and `bench-f` fails on the missing `numcodecs` module, both on both sides |
| Phase 1, 2, 3c-a | `outputs/w4-2-20261031-03` (base made a git checkout, those steps rerun) | all pass on both; backends compare: 213 leaves equal, the only failures are 3 `rust_seconds` |
| `tests/test_p5_memory.py` decode identity | the suite's `p5-memory` step, both sides; the post-merge targeted run | pass |
| Out-of-order blocks (W4R-09) | `a02_out_of_order-{base,head}.log` | **base:** `read_rows_into` raises "blosc blocks 0+1 … failed"; `plan_runs` gives inverted byte ranges (`(0, 1, 1340, 1080)`); F-order and `>i4` metadata are accepted. **head:** both readers equal the rows, the plan is the whole chunk, and both kinds of metadata are refused |
| `rang-core check` runs the two new steps | WSL `outputs/w4-2-20261031-check-all.log`; Windows `outputs/w4-2-20261031-05/windows-check.log` | see "Checks" |
| `tests/test_pc1_preconditions.py` | targeted run after the merge, and inside both checks | pass |

## Added check time (W4-7)

Measured in a throwaway `CARGO_TARGET_DIR` on WSL with 4 build jobs on a host
also running other tasks (load about 8). Logs in
`outputs/w4-2-20261031-04/gpu-cost.tsv`.

| Step | Cold | Warm |
| --- | ---: | ---: |
| `core-clippy` (existing, for scale) | 20.5 s | – |
| `core-test` (existing, for scale) | 255.0 s | – |
| `core-clippy-gpu` | 48.4 s | 0.5 s |
| `core-test-gpu` | 314.9 s | 2.4 s |

Cold, the gpu feature adds 363 s (6.1 min), more than the 3-minute bound,
and 823 MB of target directory. The two steps can therefore be left out:
`rang-core check --skip core-clippy-gpu,core-test-gpu`. The `--skip` option
already existed; the docstring and the CONTRIBUTING hunk now say so. They
stay in the default step list, because warm they cost 3 s and the gate is
their purpose. On Linux, `core-test-gpu` runs 136 tests (130 without the
feature); its 6 GPU tests print `skipped: …` and pass without an adapter.

## Checks

Both final checks ran on the tree of `aac6af8` (branch with `main` `9813608` merged;
later commits touch only this report). `main` `cd84a8e` does not touch this task's
files.

- **WSL:** `bash tools/check-all.sh`, plain:
  `## overall: PASS`, 17 steps, `core-test-gpu` 139 tests (GPU tests skip
  without an adapter), pytest 787 passed, 20 skipped.
  Log `outputs/w4-2-20261102-check-all-2.log`. An earlier run on the merge
  with `d03a95a` also passed: 780 passed, 20 skipped
  (`outputs/w4-2-20261102-check-all.log`).
- **Windows** (native, RTX 4070 Ti, Rust 1.93 MSVC):
  `.venv\Scripts\python -m rang.check` in
  `C:\Users\gijsm\Worktrees\rang\w4-2-boundaries`:
  `## overall: PASS`, 17 steps, `core-test-gpu` 139 tests, pytest 753
  passed, 54 skipped (`windows-check-4.log`).
  Logs in `outputs/w4-2-20261031-05/`.
  - The GPU tests really run there. A direct `cargo test --features gpu
    gpu:: -- --nocapture` passes 6 of 6 with no `skipped:` line, including
    `gpu_fft_matches_rustfft` and
    `gpu_inversion_matches_the_cpu_and_ignores_batching`
    (`windows-gpu-tests.log`).
  - Two setup items on the way to PASS, both independent of this task's
    checks:
    1. This host's `core.autocrlf=true` gives CRLF working files, and 20
       `test_p11_extract` cases then fail (the state X2 recorded). The
       Windows worktree was checked out with `-c core.autocrlf=false`.
    2. Four `test_df2c_campaign_gridder` cases failed on a pre-existing
       portability bug in the run scripts (`str(Path)` backslashes; `None`
       from `mem_available_gib`). It is fixed here; see "Deviations".

## Deviations

- `core/py/src/clean.rs` is not in the owner list. Its six `as_slice` calls
  needed the same C-order check for "every binding", so the change is one
  import line and those six calls. The hunk is listed for the coordinator.
- `CONTRIBUTING.md` is the coordinator's; the hunk is below.
- I did not edit the `extern "C"` functions without `catch_unwind` in files
  outside the owner list (`ffi_wgridder.rs` `kernel_row` and `last_error`,
  `ffi_closure.rs` `last_error`); see above. Nothing in them panics except a
  `RefCell` borrow.
- `MsWriter.put` and `put_cell` take `PyReadonlyArray1<u8>`. A contiguous 1-D
  array is always C-ordered, so they are unchanged.
- The identity reference is a same-host run of `ecccbf0` (P11's suite without
  coverage), not the archived P11 dirs, which predate later merges. The
  comparators in that suite compare against the archives themselves.
- `examples/run_luno_array.py`, `run_luno_1830.py`, `run_l1m.py` and
  `run_c1.py` are outside the owner list. DF2c's test fails on native Windows
  because of them, and the acceptance requires `python -m rang.check` to pass
  there, so the fix is two small changes (`as_posix()`, a `None` guard). The
  same `str(...).startswith("outputs/")` pattern remains in 17 other example
  scripts that no test exercises: `validate_core_phase1`, `validate_core_phase2`,
  `validate_core_phase3c_a`, `fetch_luno_slice`, `fetch_luno_1830`,
  `prototype_section6`, `check_luno_campaign`, `check_luno_array`,
  `check_luno_1830`, `run_core_campaign`, `run_core_injections`,
  `run_luno_campaign`, `precondition_luno_array`, `precondition_luno_campaign`,
  `precondition_luno_1830`, `bench_p1_solver` and
  `build_core_trend_mirror`. Those are left for W4-6 or a later portability
  pass. The unguarded `MemAvailable` print in `run_l5_solver_study.py` and
  `run_c1.py` was not checked.
- The identity suite was run at the first merge point (`ecccbf0` against this
  branch before any merge). It was not repeated after merging W4-1, W4-3,
  W4-5 and E6. Those merges bring their own verified changes, and the only
  overlap with this task is one conflict in `solve_complex`, where the checks
  and W4-1's options were both kept. After the merges,
  `tests/test_p1_solver.py`, `test_core_backends.py` and `test_p5_memory.py`
  pass, and so does the full check on both platforms.
- The `fetch_slice` client fix is outside the five listed items. It is a
  real latent bug, and it was found because the new fetch test is the
  second `fetch_slice` call in one process.

## Tool runs

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-31 | uv venv + editable install (WSL) | worktree | 226 s | – | includes the extension build |
| 2026-10-31 | `maturin develop --release` (WSL) | after the Rust changes | 187 s | – | 73 s at setup, 50 s after the merge |
| 2026-10-31 | fmt, clippy core and ext, blosc tests (WSL) | branch | 198 s | – | all pass |
| 2026-10-31 | pytest full (WSL, cargo not on PATH) | branch, first build | 306 s | – | 721 passed; 9 `test_core_closure` failures from the missing `cargo` (pre-W4-3 standalone build) |
| 2026-10-31 | base `ecccbf0` unpack + venv + build | `~/Build/tmp` | 198 s | – | identity reference |
| 2026-10-31 | identity suite, base / head | 33 steps | 244 s / 249 s | 1.9 GB (phase3c-a) | statuses equal |
| 2026-10-31 | `rang-core backends compare` | base vs head | 7 s | – | 572 non-numerical failures, 0 numerical |
| 2026-10-31 | phase1/2/3c-a + bench-f rerun, base and head | git-checkout base | about 60 s | – | identical but for 3 `rust_seconds` |
| 2026-10-31 | cold gpu cost (clippy, test, both features) | throwaway target | 639 s | – | table above |
| 2026-10-31 | targeted pytest after the merge (9 files) | branch + `fdf186b` | 41 s | – | 83 passed |
| 2026-10-31 | Windows uv venv + editable install | Windows worktree | 258 s | – | includes the extension build |
| 2026-10-31 | Windows `python -m rang.check`, first run | CRLF checkout, branch + `fdf186b` | not recorded | – | FAIL: 20 `test_p11_extract` (CRLF), 4 df2c (run scripts); cold GPU steps pass, 136 tests |
| 2026-11-02 | Windows `python -m rang.check`, LF checkout | branch + `d03a95a` | 1,829 s | – | FAIL: 4 df2c (run scripts) |
| 2026-11-02 | Windows `python -m rang.check`, LF checkout | branch + `9813608`, `as_posix` only | 1,843 s | – | FAIL: 1 df2c (`None` from `mem_available_gib`) |
| 2026-11-02 | Windows `cargo test --features gpu gpu:: --nocapture` | RTX 4070 Ti | 353 s (build included) | – | 6 of 6 pass, no skip |
| 2026-11-02 | Windows `python -m rang.check`, final | final code | 1,008 s | – | PASS, 753 passed, 54 skipped |
| 2026-11-02 | WSL `tools/check-all.sh` | branch + `d03a95a` | 3,013 s (with lock wait) | – | PASS, 780 passed, 20 skipped |
| 2026-11-02 | WSL `tools/check-all.sh`, final | final code | 4,117 s (with lock wait) | – | PASS, 787 passed, 20 skipped |

## For the coordinator

- **Coordinator-file hunks.** `core/py/src/lib.rs` has 26 hunks and
  `core/py/src/clean.rs` has 1, all verbatim in the appendix
  (`git diff main HEAD -- core/py/src/lib.rs core/py/src/clean.rs` after
  merging `main` at `9813608`). They do not reorder or reformat the file.
  - `solve_complex` gets one contiguous block after W4-1's new signature,
    before its `options` unpacking.
  - W4-3's `closure_scores`/`fluxstd_eval` block is unchanged: it was
    checked, and it already uses `exact_input`/`exact_output` (shape and
    standard layout).
  - The only merge conflict was in `solve_complex` (W4-1's options lines
    and this check block). Both sides were kept: the checks first, then the
    options.
- **`CONTRIBUTING.md` hunk.** After the line
  `cargo fmt --check --manifest-path core/Cargo.toml`, add:

  ```sh
  cargo clippy --offline --all-targets --manifest-path core/Cargo.toml --features gpu -- -D warnings
  cargo test --offline --release --manifest-path core/Cargo.toml --features gpu  # GPU tests skip without an adapter
  ```

  After the paragraph ending "on Windows run `.venv\Scripts\python -m
  rang.check`.", add:

  > The steps `core-clippy-gpu` and `core-test-gpu` build the core's `gpu`
  > feature (wgpu): about 6 minutes cold, a few seconds warm. Leave them
  > out with `rang-core check --skip core-clippy-gpu,core-test-gpu`.

- **STATE paragraph:** "W4-2 and W4-7 boundary checks and GPU gate (big plan
  wave 4), 2026-11-02 (implemented; measured;
  [w4-2-boundaries.md](w4-2-boundaries.md)). Every `rang._core` binding now
  refuses arrays that are not C-contiguous, and arrays of the wrong length,
  with a ValueError naming the argument. Size products are checked. The
  review's r01 out-of-bounds write and the transposed Fortran-ordered `uvw`
  now raise. Changes in the wrappers and core:
  - `flag_rows` checks its per-row arrays.
  - The blosc span decoders refuse rows outside the decoded blocks.
  - `fluxstd_eval` catches panics.
  - Zarr metadata with Fortran order, big-endian or unexpected dtypes is
    refused.
  - `core_fetch` shares `core_zarr`'s block table and its fallback for
    out-of-order blocks.

  The identity suite is numerically identical to `ecccbf0`: 282 arrays,
  88 FITS HDUs and 22,500 JSON leaves, with C, D, I, K and P5 passing.
  `rang-core check` gains `core-clippy-gpu` and `core-test-gpu`: 6.1 min
  cold, 3 s warm, skippable with `--skip`."
- **`research/README.md` index line:** "- [w4-2-boundaries.md](w4-2-boundaries.md)
  — W4-2/W4-7: sized, C-order and overflow checks on every extension
  binding; flag_rows lengths; span-row coverage; zarr order/dtype checks
  and the out-of-order fallback in core_fetch; the gpu feature in
  `rang-core check`."
- **`research/tool-timings.md` rows:** the "Tool runs" table above.
- **Ignored output directories** (main `outputs/`):
  - `w4-2-20261031-01`: the r01/r06 and out-of-order acceptance scripts and
    logs;
  - `w4-2-20261031-02`: the identity suites `base`/`head`, the backends
    receipt, `classified.json` and `classify.py`;
  - `w4-2-20261031-03`: the phase 1/2/3c-a rerun on a git-checkout base;
  - `w4-2-20261031-04`: the gpu cost logs and `gpu-cost.tsv`;
  - `w4-2-20261031-05`: the Windows check logs and JSON;
  - `w4-2-20261102-check-all.log` and `w4-2-20261102-check-all-2.log`.
  All are small except the suites (the FITS and npz outputs of two runs).
  They can be deleted once the merge is accepted.

## Appendix: coordinator-file hunks

Against `main` `9813608`. Blank context lines have lost their single leading
space (no trailing whitespace in this file); regenerate with `git diff 9813608
HEAD -- core/py/src/lib.rs core/py/src/clean.rs` if a patch is needed.

```diff
diff --git a/core/py/src/clean.rs b/core/py/src/clean.rs
index a86221a..80fc00c 100644
--- a/core/py/src/clean.rs
+++ b/core/py/src/clean.rs
@@ -10,7 +10,7 @@
 //! `CYCLE_COLUMNS` per major cycle; a `SUMMARY`-long summary). Returns 0, or
 //! 1 when an array has the wrong length; a driver error raises `ValueError`.

-use crate::{Ro, Rw, detach};
+use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
 use pyo3::exceptions::PyValueError;
 use pyo3::prelude::*;
 use rang_core::clean_certified::{
@@ -88,13 +88,19 @@ pub fn clean_certified(
         return Ok(1);
     };
     let (uvw, freq, vis, wgt) = (
-        uvw.as_slice()?,
-        freq.as_slice()?,
-        vis.as_slice()?,
-        wgt.as_slice()?,
+        c_slice(&uvw, "uvw")?,
+        c_slice(&freq, "freq")?,
+        c_slice(&vis, "vis")?,
+        c_slice(&wgt, "wgt")?,
+    );
+    let (model, residual) = (
+        c_slice_mut(&mut model, "model")?,
+        c_slice_mut(&mut residual, "residual")?,
+    );
+    let (cycles, summary) = (
+        c_slice_mut(&mut cycles, "cycles")?,
+        c_slice_mut(&mut summary, "summary")?,
     );
-    let (model, residual) = (model.as_slice_mut()?, residual.as_slice_mut()?);
-    let (cycles, summary) = (cycles.as_slice_mut()?, summary.as_slice_mut()?);
     let rule = match rule {
         0 => MinorRule::Clark,
         1 => MinorRule::Provable,
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 7fa057c..a73611d 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -28,6 +28,7 @@ use numpy::{
     Complex32, Complex64, Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn,
     PyReadwriteArrayDyn,
 };
+use numpy::{PyReadonlyArray, PyReadwriteArray, PyUntypedArrayMethods, ndarray::Dimension};
 #[cfg(feature = "gpu")]
 use pyo3::exceptions::PyRuntimeError;
 use pyo3::exceptions::{PyOSError, PyValueError};
@@ -79,9 +80,86 @@ fn detach<R, F: FnOnce() -> R>(py: Python<'_>, f: F) -> R {
     py.detach(move || Detached(job.run())).0
 }

+/// The slice of a C-contiguous input array (task W4-2, W4R-04): rust-numpy's
+/// `as_slice` also accepts a Fortran-ordered array, which a kernel would read
+/// transposed, so that is a ValueError naming the argument.
+fn c_slice<'a, T: Element, D: Dimension>(
+    a: &'a PyReadonlyArray<'_, T, D>,
+    name: &str,
+) -> PyResult<&'a [T]> {
+    if !a.is_c_contiguous() {
+        return Err(PyValueError::new_err(format!(
+            "{name} must be C-contiguous"
+        )));
+    }
+    Ok(a.as_slice()?)
+}
+
+/// The slice of a C-contiguous output array (as `c_slice`).
+fn c_slice_mut<'a, T: Element, D: Dimension>(
+    a: &'a mut PyReadwriteArray<'_, T, D>,
+    name: &str,
+) -> PyResult<&'a mut [T]> {
+    if !a.is_c_contiguous() {
+        return Err(PyValueError::new_err(format!(
+            "{name} must be C-contiguous"
+        )));
+    }
+    Ok(a.as_slice_mut()?)
+}
+
+/// The product of buffer sizes, or a ValueError naming it on overflow (W4-2).
+fn size(name: &str, factors: &[usize]) -> PyResult<usize> {
+    factors
+        .iter()
+        .try_fold(1usize, |p, &f| p.checked_mul(f))
+        .ok_or_else(|| PyValueError::new_err(format!("{name} overflows")))
+}
+
+/// Pointer of a C-contiguous input `name` of exactly `len` elements, else a
+/// ValueError naming it (W4-2).
+fn arg<T: Element>(a: &Ro<'_, T>, name: &str, len: usize) -> PyResult<*const T> {
+    let s = c_slice(a, name)?;
+    if s.len() != len {
+        return Err(PyValueError::new_err(format!(
+            "{name} must hold {len} elements, not {}",
+            s.len()
+        )));
+    }
+    Ok(s.as_ptr())
+}
+
+/// As `arg` for an optional input; null when absent.
+fn opt_arg<T: Element>(a: &Option<Ro<'_, T>>, name: &str, len: usize) -> PyResult<*const T> {
+    match a {
+        None => Ok(std::ptr::null()),
+        Some(a) => arg(a, name, len),
+    }
+}
+
+/// As `arg` for an output.
+fn arg_mut<T: Element>(a: &mut Rw<'_, T>, name: &str, len: usize) -> PyResult<*mut T> {
+    let s = c_slice_mut(a, name)?;
+    if s.len() != len {
+        return Err(PyValueError::new_err(format!(
+            "{name} must hold {len} elements, not {}",
+            s.len()
+        )));
+    }
+    Ok(s.as_mut_ptr())
+}
+
+/// As `arg_mut` for an optional output; null when absent.
+fn opt_arg_mut<T: Element>(a: &mut Option<Rw<'_, T>>, name: &str, len: usize) -> PyResult<*mut T> {
+    match a {
+        None => Ok(std::ptr::null_mut()),
+        Some(a) => arg_mut(a, name, len),
+    }
+}
+
 /// Borrowed pointer of a required input array.
 fn ptr<T: Element>(a: &Ro<'_, T>) -> PyResult<*const T> {
-    Ok(a.as_slice()?.as_ptr())
+    Ok(c_slice(a, "array")?.as_ptr())
 }

 /// Borrowed pointer of an optional input array; null when absent.
@@ -94,7 +172,7 @@ fn opt_ptr<T: Element>(a: &Option<Ro<'_, T>>) -> PyResult<*const T> {

 /// Borrowed pointer of a required output array.
 fn ptr_mut<T: Element>(a: &mut Rw<'_, T>) -> PyResult<*mut T> {
-    Ok(a.as_slice_mut()?.as_mut_ptr())
+    Ok(c_slice_mut(a, "array")?.as_mut_ptr())
 }

 /// Borrowed pointer of an optional output array; null when absent.
@@ -107,13 +185,13 @@ fn opt_ptr_mut<T: Element>(a: &mut Option<Rw<'_, T>>) -> PyResult<*mut T> {

 /// Pointer of an input that must hold exactly `len` elements.
 fn sized<T: Element>(a: &Ro<'_, T>, len: usize) -> PyResult<Option<*const T>> {
-    let s = a.as_slice()?;
+    let s = c_slice(a, "array")?;
     Ok((s.len() == len).then_some(s.as_ptr()))
 }

 /// Pointer of an output that must hold exactly `len` elements.
 fn sized_mut<T: Element>(a: &mut Rw<'_, T>, len: usize) -> PyResult<Option<*mut T>> {
-    let s = a.as_slice_mut()?;
+    let s = c_slice_mut(a, "array")?;
     Ok((s.len() == len).then_some(s.as_mut_ptr()))
 }

@@ -122,7 +200,7 @@ fn sized_mut<T: Element>(a: &mut Rw<'_, T>, len: usize) -> PyResult<Option<*mut
 #[pyfunction]
 fn data_address(array: &Bound<'_, PyAny>) -> PyResult<usize> {
     fn address<T: Element>(a: Ro<'_, T>) -> PyResult<usize> {
-        Ok(a.as_slice()?.as_ptr() as usize)
+        Ok(c_slice(&a, "array")?.as_ptr() as usize)
     }
     if let Ok(a) = array.extract::<Ro<'_, f32>>() {
         return address(a);
@@ -179,35 +257,49 @@ fn fused(
     mut diag_count: Option<Rw<'_, u64>>,
     mut split_stats: Rw<'_, f64>,
 ) -> PyResult<i32> {
+    let cells = size("nrow * nchan", &[nrow, nchan])?;
+    let ngain = size(
+        "ntime_bins * nfreq_bins * nant",
+        &[ntime_bins, nfreq_bins, nant],
+    )?;
+    let (c8, g8, g64) = (
+        size("8 * nrow * nchan", &[8, cells])?,
+        size("8 * gains", &[8, ngain])?,
+        size("64 * gains", &[64, ngain])?,
+    );
     let inputs = ffi::FusedInputs {
         nrow,
         nchan,
         ntime_bins,
         nfreq_bins,
         nant,
-        data: ptr(&data)?,
-        weights: ptr(&weights)?,
-        model_stored: opt_ptr(&model_stored)?,
-        model_scalar: opt_ptr(&model_scalar)?,
-        antenna1: ptr(&antenna1)?,
-        antenna2: ptr(&antenna2)?,
-        time_bin: ptr(&time_bin)?,
-        freq_bin: ptr(&freq_bin)?,
-        gains: ptr(&gains)?,
-        gain_valid: ptr(&gain_valid)?,
-        split: ptr(&split)?,
+        data: arg(&data, "data", c8)?,
+        weights: arg(&weights, "weights", 4 * cells)?,
+        model_stored: opt_arg(&model_stored, "model_stored", c8)?,
+        model_scalar: opt_arg(&model_scalar, "model_scalar", nchan)?,
+        antenna1: arg(&antenna1, "antenna1", nrow)?,
+        antenna2: arg(&antenna2, "antenna2", nrow)?,
+        time_bin: arg(&time_bin, "time_bin", nrow)?,
+        freq_bin: arg(&freq_bin, "freq_bin", nchan)?,
+        gains: arg(&gains, "gains", g8)?,
+        gain_valid: arg(&gain_valid, "gain_valid", ngain)?,
+        split: arg(&split, "split", cells)?,
     };
     let mut outputs = ffi::FusedOutputs {
-        residuals: opt_ptr_mut(&mut residuals)?,
-        scores: opt_ptr_mut(&mut scores)?,
-        diag_h: opt_ptr_mut(&mut diag_h)?,
-        diag_b: opt_ptr_mut(&mut diag_b)?,
-        diag_count: opt_ptr_mut(&mut diag_count)?,
-        split_stats: ptr_mut(&mut split_stats)?,
+        residuals: opt_arg_mut(&mut residuals, "residuals", c8)?,
+        scores: opt_arg_mut(&mut scores, "scores", cells)?,
+        diag_h: opt_arg_mut(&mut diag_h, "diag_h", g64)?,
+        diag_b: opt_arg_mut(&mut diag_b, "diag_b", g8)?,
+        diag_count: opt_arg_mut(&mut diag_count, "diag_count", ngain)?,
+        split_stats: arg_mut(
+            &mut split_stats,
+            "split_stats",
+            4 * rang_core::fused::SPLITS,
+        )?,
     };
-    // SAFETY: every pointer borrows a live, contiguous NumPy buffer held by
-    // the arguments for the duration of the call; the Python wrapper sizes
-    // them as the C ABI documents.
+    // SAFETY: every pointer borrows a live, C-contiguous NumPy buffer held by
+    // the arguments for the duration of the call, of the length the C ABI
+    // documents (checked above).
     Ok(detach(py, || unsafe {
         ffi::rang_core_fused(&inputs, &mut outputs)
     }))
@@ -260,6 +352,28 @@ fn solve_complex(
     options: (u8, u8, f64, usize, u8),
     trace: Option<String>,
 ) -> PyResult<(i32, usize, f64)> {
+    // Every buffer's length and order (task W4-2): a ValueError naming it.
+    let cells = size("nrow * nchan", &[nrow, nchan])?;
+    let ngain = size(
+        "ntime_bins * nfreq_bins * nant",
+        &[ntime_bins, nfreq_bins, nant],
+    )?;
+    let (c8, g8) = (
+        size("8 * nrow * nchan", &[8, cells])?,
+        size("8 * gains", &[8, ngain])?,
+    );
+    arg(&data, "data", c8)?;
+    arg(&weights, "weights", 4 * cells)?;
+    opt_arg(&model_stored, "model_stored", c8)?;
+    opt_arg(&model_scalar, "model_scalar", nchan)?;
+    arg(&flag, "flag", 4 * cells)?;
+    arg(&flag_row, "flag_row", nrow)?;
+    arg(&antenna1, "antenna1", nrow)?;
+    arg(&antenna2, "antenna2", nrow)?;
+    arg(&time_bin, "time_bin", nrow)?;
+    arg(&freq_bin, "freq_bin", nchan)?;
+    arg_mut(&mut gains, "gains", g8)?;
+    arg_mut(&mut flags, "flags", ngain)?;
     let (transposed_qp_weights, stop, tolerance, anderson, freeze) = options;
     let trace = trace.unwrap_or_default();
     let inputs = ffi::SolveInputs {
@@ -327,24 +441,37 @@ fn predict_components(
     mut vis: Rw<'_, f64>,
     mut spectra: Option<Rw<'_, f64>>,
 ) -> PyResult<i32> {
+    let (r3, s2, s3) = (
+        size("3 * nrow", &[3, nrow])?,
+        size("2 * nsrc", &[2, nsrc])?,
+        size("3 * nsrc", &[3, nsrc])?,
+    );
     let inputs = ffi::PredictInputs {
         nrow,
         nchan,
         nsrc,
         ncoeff,
-        uvw: ptr(&uvw)?,
-        frequency: ptr(&frequency)?,
-        lm: ptr(&lm)?,
-        kind: ptr(&kind)?,
-        flux: ptr(&flux)?,
-        coeffs: ptr(&coeffs)?,
-        log_poly: ptr(&log_poly)?,
-        ref_freq: ptr(&ref_freq)?,
-        gauss_shape: ptr(&gauss_shape)?,
+        uvw: arg(&uvw, "uvw", r3)?,
+        frequency: arg(&frequency, "frequency", nchan)?,
+        lm: arg(&lm, "lm", s2)?,
+        kind: arg(&kind, "kind", nsrc)?,
+        flux: arg(&flux, "flux", nsrc)?,
+        coeffs: arg(&coeffs, "coeffs", size("nsrc * ncoeff", &[nsrc, ncoeff])?)?,
+        log_poly: arg(&log_poly, "log_poly", nsrc)?,
+        ref_freq: arg(&ref_freq, "ref_freq", nsrc)?,
+        gauss_shape: arg(&gauss_shape, "gauss_shape", s3)?,
     };
     let mut outputs = ffi::PredictOutputs {
-        vis: ptr_mut(&mut vis)?,
-        spectra: opt_ptr_mut(&mut spectra)?,
+        vis: arg_mut(
+            &mut vis,
+            "vis",
+            size("2 * nrow * nchan", &[2, nrow, nchan])?,
+        )?,
+        spectra: opt_arg_mut(
+            &mut spectra,
+            "spectra",
+            size("nsrc * nchan", &[nsrc, nchan])?,
+        )?,
     };
     // SAFETY: as in `fused`.
     Ok(detach(py, || unsafe {
@@ -395,10 +522,11 @@ fn blosc_decode_rows<'py>(
     row_bytes: usize,
     rows: Ro<'_, usize>,
 ) -> PyResult<(i32, usize, Bound<'py, PyBytes>)> {
-    let rows = rows.as_slice()?;
+    let rows = c_slice(&rows, "rows")?;
     let mut status = 0;
     let mut blocks = 0usize;
-    let out = PyBytes::new_with(py, rows.len() * row_bytes, |buf| {
+    let nbytes = size("len(rows) * row_bytes", &[rows.len(), row_bytes])?;
+    let out = PyBytes::new_with(py, nbytes, |buf| {
         // SAFETY: `buf` holds `nrows * row_bytes` bytes; `rows` is live.
         status = detach(py, || unsafe {
             ffi::rang_core_blosc_decode_rows(
@@ -436,7 +564,7 @@ fn blosc_decode_block(
     block: &[u8],
     mut out: Rw<'_, u8>,
 ) -> PyResult<i32> {
-    let out = out.as_slice_mut()?;
+    let out = c_slice_mut(&mut out, "out")?;
     // SAFETY: every slice is live for the call.
     Ok(detach(py, || unsafe {
         ffi::rang_core_blosc_decode_block(
@@ -465,9 +593,9 @@ fn blosc_decode_span_rows(
     rows: Ro<'_, usize>,
     mut out: Rw<'_, u8>,
 ) -> PyResult<i32> {
-    let rows = rows.as_slice()?;
-    let out = out.as_slice_mut()?;
-    if out.len() != rows.len() * row_bytes {
+    let rows = c_slice(&rows, "rows")?;
+    let out = c_slice_mut(&mut out, "out")?;
+    if Some(out.len()) != rows.len().checked_mul(row_bytes) {
         return Ok(1);
     }
     // SAFETY: every slice is live for the call and `out` has the documented length.
@@ -516,25 +644,34 @@ fn correct_stokes_i(
     let Some(cells) = nrow.checked_mul(nchan) else {
         return Ok(1);
     };
-    let gains = ntime_bins * nfreq_bins * nant;
+    // `8 * cells` and `8 * gains` below must not wrap either (W4-2).
+    let Ok(gains) = size("gains", &[ntime_bins, nfreq_bins, nant]) else {
+        return Ok(1);
+    };
+    if cells.checked_mul(8).is_none() || gains.checked_mul(8).is_none() {
+        return Ok(1);
+    }
     let (data, weights, flags, flag_row) = (
-        data.as_slice()?,
-        weights.as_slice()?,
-        flags.as_slice()?,
-        flag_row.as_slice()?,
+        c_slice(&data, "data")?,
+        c_slice(&weights, "weights")?,
+        c_slice(&flags, "flags")?,
+        c_slice(&flag_row, "flag_row")?,
     );
     let added = match &added {
-        Some(a) => Some(a.as_slice()?),
+        Some(a) => Some(c_slice(a, "added")?),
         None => None,
     };
     let (antenna1, antenna2, time_bin, freq_bin) = (
-        antenna1.as_slice()?,
-        antenna2.as_slice()?,
-        time_bin.as_slice()?,
-        freq_bin.as_slice()?,
+        c_slice(&antenna1, "antenna1")?,
+        c_slice(&antenna2, "antenna2")?,
+        c_slice(&time_bin, "time_bin")?,
+        c_slice(&freq_bin, "freq_bin")?,
+    );
+    let (inverse, valid) = (c_slice(&inverse, "inverse")?, c_slice(&valid, "valid")?);
+    let (sample, weight) = (
+        c_slice_mut(&mut sample, "sample")?,
+        c_slice_mut(&mut weight, "weight")?,
     );
-    let (inverse, valid) = (inverse.as_slice()?, valid.as_slice()?);
-    let (sample, weight) = (sample.as_slice_mut()?, weight.as_slice_mut()?);
     if data.len() != 8 * cells
         || weights.len() != 4 * cells
         || flags.len() != 4 * cells
@@ -595,8 +732,8 @@ fn blosc_decode_span_rows_strided(
     offset: usize,
     stride: usize,
 ) -> PyResult<i32> {
-    let (span, rows) = (span.as_slice()?, rows.as_slice()?);
-    let out = out.as_slice_mut()?;
+    let (span, rows) = (c_slice(&span, "span")?, c_slice(&rows, "rows")?);
+    let out = c_slice_mut(&mut out, "out")?;
     if offset > out.len() {
         return Ok(1);
     }
@@ -653,15 +790,16 @@ fn stokes_i(
     mut vis: Rw<'_, f32>,
     mut weight: Rw<'_, f32>,
 ) -> PyResult<i32> {
+    let c4 = size("4 * ncell", &[4, ncell])?;
     let inputs = StokesIInputs {
         ncell,
-        data: ptr(&data)?,
-        weights: ptr(&weights)?,
-        flags: ptr(&flags)?,
+        data: arg(&data, "data", size("8 * ncell", &[8, ncell])?)?,
+        weights: arg(&weights, "weights", c4)?,
+        flags: arg(&flags, "flags", c4)?,
     };
     let mut outputs = StokesIOutputs {
-        vis: ptr_mut(&mut vis)?,
-        weight: ptr_mut(&mut weight)?,
+        vis: arg_mut(&mut vis, "vis", 2 * ncell)?,
+        weight: arg_mut(&mut weight, "weight", ncell)?,
     };
     // SAFETY: as in `fused`.
     Ok(detach(py, || unsafe {
@@ -693,13 +831,22 @@ fn imaging_weights(
     mut grid: Option<Rw<'_, f64>>,
     mut sums: Option<Rw<'_, f64>>,
 ) -> PyResult<i32> {
+    let cells = size("nrow * nchan", &[nrow, nchan])?;
+    // The grid's length follows `rang_core_weight_grid_shape`; with an
+    // invalid super weight the kernel returns 1 before writing it.
+    let grid_len = if super_weight > 0.0 {
+        let (w, h) = rang_core::weights::WeightGrid::shape(width, height, super_weight);
+        size("grid width * height", &[w, h])? / 2
+    } else {
+        0
+    };
     let inputs = ImagingWeightInputs {
         nrow,
         nchan,
-        uvw: ptr(&uvw)?,
-        wavelength: ptr(&wavelength)?,
-        weights: ptr(&weights)?,
-        row_selected: ptr(&row_selected)?,
+        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
+        wavelength: arg(&wavelength, "wavelength", nchan)?,
+        weights: arg(&weights, "weights", cells)?,
+        row_selected: arg(&row_selected, "row_selected", nrow)?,
         class,
         robust,
         width,
@@ -711,9 +858,13 @@ fn imaging_weights(
         rank_filter_size,
     };
     let mut outputs = ImagingWeightOutputs {
-        weights: ptr_mut(&mut out_weights)?,
-        grid: opt_ptr_mut(&mut grid)?,
-        sums: opt_ptr_mut(&mut sums)?,
+        weights: arg_mut(&mut out_weights, "out_weights", cells)?,
+        grid: if super_weight > 0.0 {
+            opt_arg_mut(&mut grid, "grid", grid_len)?
+        } else {
+            opt_ptr_mut(&mut grid)?
+        },
+        sums: opt_arg_mut(&mut sums, "sums", 4)?,
     };
     // SAFETY: as in `fused`.
     Ok(detach(py, || unsafe {
@@ -745,6 +896,8 @@ fn grid_invert(
     mut psf: Rw<'_, f64>,
     mut stats: Rw<'_, f64>,
 ) -> PyResult<i32> {
+    let cells = size("nrow * nchan", &[nrow, nchan])?;
+    let pixels = size("width * height", &[width, height])?;
     let inputs = GridInputs {
         nrow,
         nchan,
@@ -756,16 +909,16 @@ fn grid_invert(
         pixel_size_x,
         pixel_size_y,
         padding,
-        uvw: ptr(&uvw)?,
-        frequencies: ptr(&frequencies)?,
-        data: ptr(&data)?,
-        weights: ptr(&weights)?,
-        imaging_weights: ptr(&imaging_weights)?,
+        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
+        frequencies: arg(&frequencies, "frequencies", nchan)?,
+        data: arg(&data, "data", size("2 * nrow * nchan", &[2, cells])?)?,
+        weights: arg(&weights, "weights", cells)?,
+        imaging_weights: arg(&imaging_weights, "imaging_weights", cells)?,
     };
     let mut outputs = GridOutputs {
-        dirty: ptr_mut(&mut dirty)?,
-        psf: ptr_mut(&mut psf)?,
-        stats: ptr_mut(&mut stats)?,
+        dirty: arg_mut(&mut dirty, "dirty", pixels)?,
+        psf: arg_mut(&mut psf, "psf", pixels)?,
+        stats: arg_mut(&mut stats, "stats", rang_core::ffi_grid::N_STATS)?,
     };
     // SAFETY: as in `fused`.
     Ok(detach(py, || unsafe {
@@ -804,9 +957,8 @@ fn grid_invert_gpu(
     mut timings: Rw<'_, f64>,
 ) -> PyResult<i32> {
     let precision = rang_core::gpu::Precision::parse(precision).map_err(PyValueError::new_err)?;
-    if timings.as_slice()?.len() != rang_core::gpu::ffi::N_TIMINGS {
-        return Err(PyValueError::new_err("timings must hold N_TIMINGS doubles"));
-    }
+    let cells = size("nrow * nchan", &[nrow, nchan])?;
+    let pixels = size("width * height", &[width, height])?;
     let inputs = GridInputs {
         nrow,
         nchan,
@@ -818,18 +970,18 @@ fn grid_invert_gpu(
         pixel_size_x,
         pixel_size_y,
         padding,
-        uvw: ptr(&uvw)?,
-        frequencies: ptr(&frequencies)?,
-        data: ptr(&data)?,
-        weights: ptr(&weights)?,
-        imaging_weights: ptr(&imaging_weights)?,
+        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
+        frequencies: arg(&frequencies, "frequencies", nchan)?,
+        data: arg(&data, "data", size("2 * nrow * nchan", &[2, cells])?)?,
+        weights: arg(&weights, "weights", cells)?,
+        imaging_weights: arg(&imaging_weights, "imaging_weights", cells)?,
     };
     let mut outputs = GridOutputs {
-        dirty: ptr_mut(&mut dirty)?,
-        psf: ptr_mut(&mut psf)?,
-        stats: ptr_mut(&mut stats)?,
+        dirty: arg_mut(&mut dirty, "dirty", pixels)?,
+        psf: arg_mut(&mut psf, "psf", pixels)?,
+        stats: arg_mut(&mut stats, "stats", rang_core::ffi_grid::N_STATS)?,
     };
-    let timings = ptr_mut(&mut timings)?;
+    let timings = arg_mut(&mut timings, "timings", rang_core::gpu::ffi::N_TIMINGS)?;
     // SAFETY: as in `fused`; `timings` holds N_TIMINGS doubles.
     detach(py, || unsafe {
         rang_core::gpu::ffi::grid_invert(&inputs, &mut outputs, precision, timings)
@@ -855,7 +1007,7 @@ fn grid_kernel(
     oversampling: usize,
     mut kernel: Rw<'_, f64>,
 ) -> PyResult<i32> {
-    let out = kernel.as_slice_mut()?;
+    let out = c_slice_mut(&mut kernel, "kernel")?;
     if Some(out.len()) != kernel_size.checked_mul(oversampling) {
         return Ok(1);
     }
@@ -1024,8 +1176,8 @@ fn wgridder_v2d<T: Element>(
     let opts = wgridder_options(&opts)?;
     let nrow = uvw.as_array().len() / 3;
     let nchan = freq.as_array().len();
-    let n = nrow * nchan;
-    let npix = opts.nx * opts.ny;
+    let n = size("nrow * nchan", &[nrow, nchan])?;
+    let npix = size("nx * ny", &[opts.nx, opts.ny])?;
     let vis = VisArg::extract(vis)?;
     let wgt = WgtArg::extract(wgt)?;
     let (vis_ptr, vis_kind) = vis.ptr_kind()?;
@@ -1156,12 +1308,12 @@ fn wgridder_d2v<T: Element>(
     let opts = wgridder_options(&opts)?;
     let nrow = uvw.as_array().len() / 3;
     let nchan = freq.as_array().len();
-    let n = nrow * nchan;
+    let n = size("nrow * nchan", &[nrow, nchan])?;
     let wgt = WgtArg::extract(wgt)?;
     let (wgt_ptr, wgt_kind) = wgt.ptr_kind()?;
     let sizes_ok = uvw.as_array().len() == nrow * 3
-        && dirty.as_array().len() == opts.nx * opts.ny
-        && vis.as_array().len() == 2 * n
+        && dirty.as_array().len() == size("nx * ny", &[opts.nx, opts.ny])?
+        && vis.as_array().len() == size("2 * nrow * nchan", &[2, n])?
         && wgt.len().is_none_or(|l| l == n)
         && mask.as_ref().is_none_or(|m| m.as_array().len() == n)
         && info.as_array().len() == rang_core::wgridder::N_INFO;
@@ -1291,6 +1443,10 @@ fn flag_rows(
     mut intensity: Option<Rw<'_, f32>>,
     mut stages: Option<Rw<'_, u8>>,
 ) -> PyResult<i32> {
+    let cells = size("nrow * nchan * ncorr", &[nrow, nchan, ncorr])?;
+    let window = size("nbl * ntime * nchan", &[nbl, ntime, nchan])?;
+    let offsets = c_slice(&mask_offsets, "mask_offsets")?;
+    let nmask_freqs = offsets.last().copied().unwrap_or(0);
     let inputs = FlagInputs {
         nrow,
         nchan,
@@ -1300,23 +1456,42 @@ fn flag_rows(
         ntime,
         nmasks,
         nsteps,
-        data: ptr(&data)?,
-        flags: ptr(&flags)?,
-        baseline_index: ptr(&baseline_index)?,
-        time_index: ptr(&time_index)?,
-        baselines: ptr(&baselines)?,
-        antenna_position: ptr(&antenna_position)?,
-        chan_freq: ptr(&chan_freq)?,
-        chan_width: ptr(&chan_width)?,
-        corr_type: ptr(&corr_type)?,
-        mask_freqs: ptr(&mask_freqs)?,
-        mask_offsets: ptr(&mask_offsets)?,
-        steps: ptr(&steps)?,
+        data: arg(&data, "data", size("2 * cells", &[2, cells])?)?,
+        flags: arg(&flags, "flags", cells)?,
+        baseline_index: arg(&baseline_index, "baseline_index", nrow)?,
+        time_index: arg(&time_index, "time_index", nrow)?,
+        baselines: arg(&baselines, "baselines", size("2 * nbl", &[2, nbl])?)?,
+        antenna_position: arg(
+            &antenna_position,
+            "antenna_position",
+            size("3 * nant", &[3, nant])?,
+        )?,
+        chan_freq: arg(&chan_freq, "chan_freq", nchan)?,
+        chan_width: arg(&chan_width, "chan_width", nchan)?,
+        corr_type: arg(&corr_type, "corr_type", ncorr)?,
+        mask_freqs: arg(&mask_freqs, "mask_freqs", nmask_freqs)?,
+        mask_offsets: arg(&mask_offsets, "mask_offsets", nmasks.saturating_add(1))?,
+        steps: arg(
+            &steps,
+            "steps",
+            size(
+                "nsteps * STEP_WIDTH",
+                &[nsteps, rang_core::ffi_flag::STEP_WIDTH],
+            )?,
+        )?,
     };
     let mut outputs = FlagOutputs {
-        flags: ptr_mut(&mut out_flags)?,
-        intensity: opt_ptr_mut(&mut intensity)?,
-        stages: opt_ptr_mut(&mut stages)?,
+        flags: arg_mut(&mut out_flags, "out_flags", cells)?,
+        intensity: opt_arg_mut(
+            &mut intensity,
+            "intensity",
+            size("2 * window", &[2, window])?,
+        )?,
+        stages: opt_arg_mut(
+            &mut stages,
+            "stages",
+            size("nsteps * window", &[nsteps, window])?,
+        )?,
     };
     // SAFETY: as in `fused`.
     Ok(detach(py, || unsafe {
```
