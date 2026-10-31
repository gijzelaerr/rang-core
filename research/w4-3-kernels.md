# Big plan task W4-3: the closure and flux-standard kernels move into the extension

Branch `w4-3-kernels` from `main` `ecccbf0`. Fix task W4-3 of the
[final review](w4-review.md), findings W4R-06 (Cargo at a kernel call) and
W4R-16 (dead fallbacks).

**Status: implemented and measured.** `rang._core` binds `closure_scores`
and `fluxstd_eval`. `rang.core_closure` and `rang.fluxstd` call them, and
nothing in the package runs Cargo any more. The standalone builders, the
ctypes fallbacks and the dead P5 branch are deleted. All acceptance items
pass:

- From a wheel in a venv without cargo, both kernels run (r05).
- On 171 arrays, the kernels are byte-identical to the standalone builds
  they replace.
- The C1 checker and the FS1 `setjy` check equal their archives except for
  wall times.
- A clean pytest run leaves no `core/target/*-standalone`.

## What changed

| File | Change | Lines added / deleted |
| --- | --- | --- |
| `core/py/src/lib.rs`* | New block before the `#[pymodule]` with two helpers and two bindings, plus two `m.add_function` lines at the end of the registration list. Nothing else in the file is touched. | +172 / 0 |
| `python/rang/core_closure.py` | The kernel is called through `core.extension().closure_scores`. `library()` and `library_path()` return the extension and its binary, so `core_campaign_closure` (receipt hashes, warm-up) is unchanged. | +10 / −158 |
| `python/rang/fluxstd.py` | `rust_library()` returns the extension. `rust_log10_poly(lib, …)` calls `lib.fluxstd_eval`. `core_log10_poly` uses the two. `examples/check_fluxstd.py` and the archive keys are therefore unchanged. | +10 / −81 |
| `python/rang/core_wgridder.py` | The ctypes fallback is gone (W4R-16), and `ctypes` is no longer imported. `extension()` is `core.extension()`, `backend()` is always `"extension"` (receipts read it), and `library_path()` is the extension's binary. `_options` returns the 18 floats directly. | +31 / −279 |
| `python/rang/core_campaign_array.py` | `correct_stokes_i` loses its unreachable `else` branch (W4R-16), and `import ctypes` goes. | +10 / −25 |
| `python/rang/core_fetch.py` | **No change.** It has no dead branch of its own. `p5_extension()` stays because `correct_stokes_i` and `tests/test_p5_memory.py` call it. The names the dead branch used (`CorrectInputs`, `p5_library`) were already gone from `core_fetch`. | 0 |
| `tests/test_fluxstd.py` | The kernel test no longer skips without cargo. | +1 / −2 |
| `tests/test_df2b_wgrid.py` | The extension test refuses `subprocess.run` and `Popen` (instead of monkeypatching `build_standalone`). It asserts that the builders, `library` and `Options` are gone. | +9 / −4 |
| `tests/test_w4_3_kernels.py` (new) | Four tests, listed after this table. | +156 |
| `tools/wheel/test.py` | A `kernels` step (described after this table). `tests/test_w4_3_kernels.py` is added to the wheel's pytest list. | +28 |
| `docs/installation.md` | The paragraph saying three modules build with cargo is gone. The text now says every kernel is in the extension and that neither import nor a kernel call runs Cargo. | +8 / −9 |

The tests in `tests/test_w4_3_kernels.py`:

1. Both kernels and `kernel_row` run with `subprocess` refused, the
   builders are absent from all three modules, and no `*-standalone`
   directory appears.
2. Bad buffers for `closure_scores` are refused:
   - a wrong dtype raises TypeError;
   - an F-order or strided array raises ValueError ("C-contiguous");
   - a short `antenna1` or `time_index`, the wrong `model` or `count` shape,
     or a last axis of `data` other than 4 raises ValueError;
   - stations outside the cycle raise ValueError with the core's message.
3. Bad buffers for `fluxstd_eval` are refused: wrong `out` length, strided
   or 2-D `freq`, float32, no coefficients, a negative frequency, and a
   read-only `out`.
4. Two threads call the closure kernel at once, and both results equal the
   serial result byte for byte.

The `kernels` step in `tools/wheel/test.py` runs in the same environment as
the smoke step, with no cargo, no `RANG_*` variables and `-I`. It makes one
closure call on 8 stations, with finite scores and 6 closures per sample
asserted. It makes one flux-standard call, checked against the Python
evaluator to within 1e-13.

\* coordinator file; the hunk is under "For the coordinator".

The four Python modules lose 543 lines and gain 61, a net −482. That is
more than the review's "about 400" because the wgridder fallback had
ctypes calls in each entry point as well as the builder. The whole branch
diff is +435 / −558.

### The bindings

`closure_scores(data, model, weights, usable, antenna1, antenna2,
time_index, stations, nant, ntime, family, min_closures, reroute, residual,
tv, count)` and `fluxstd_eval(coeffs, unit_hz, freq, out)` follow the DF2b
wgridder pattern:

- The arrays are typed. complex64 `data` and `model`; float32 `weights`,
  `residual` and `tv`; uint8 `usable`; uint32 row columns and stations;
  uint16 `count`; float64 for the flux standards. A wrong dtype is a
  TypeError from PyO3's conversion.
- `exact_input` and `exact_output` require standard (C) layout and the
  exact shape. `nrow` and `nchan` come from `data.shape`, and every other
  buffer, the outputs included, is checked against them. `as_slice` alone
  would accept an F-ordered 3-D array.
- The binding calls the same C function a C consumer would
  (`rang_core_closure_scores`, `rang_core_fluxstd_eval`), inside
  `detach` (GIL released) and `catch_unwind`. `ffi_fluxstd` has no
  `catch_unwind` of its own.
- Status 1 raises ValueError. For closures the message is the core's,
  read from the thread-local last error on the calling thread, in the
  wrapper's old format `closure kernel failed (1): …`. Status 2 (a panic)
  raises RuntimeError. `PyRuntimeError` is named by its full path,
  because the file imports it only under `cfg(feature = "gpu")`.

No `core/src/lib.rs` change was needed: `closure`, `ffi_closure`,
`fluxstd` and `ffi_fluxstd` were already listed.

## Measured acceptance (2026-10-31)

| Item | Run | Result |
| --- | --- | --- |
| Kernel parity, before and after | `outputs/w4-3-20261031-01/parity.py`. Before: the unchanged tree, standalone `librang_c1_core.so` and `fs1`. After: the extension, with `PATH=/usr/bin:/bin` (no cargo). 135 closure arrays: 5 cases × 3 families × 3 (min_closures, reroute) × 3 outputs, 103,255 NaN values included. 36 flux-standard pieces on 1,998 frequencies. | **byte-identical**, 171 of 171; digest `65af587a…` both times (`before.json`, `after.json`, `compare.json`) |
| C1 comparator (`examples/check_c1.py`; there is no `rang-core` C1 verb, see "Deviations") | `-01/c1-check-after` on the frozen run `c1-20261030-01` with PC1's precondition `pc1-20261030-10-l1-fix`, compared with the current archive `pc1-20261030-12-c1-check`; cargo off `PATH` | identical except `check_seconds` (both files). The unchanged tree gave the same (`-01/c1-check-before`) |
| FS1 `setjy` checks (`examples/check_fluxstd.py`) | `-01/fs1-after.json` against `research/results/fs1-flux-standards.json`; cargo off `PATH` | identical except `rust.wall_s_incl_build` (0.01 against 0.02 s). Before: the same, with 0.05 s |
| r05: wheel in a venv inside an unrelated git repository, `PATH=/usr/bin:/bin` | `outputs/w4-3-20261031-03-r05` (the review's driver and probe; see "Deviations") on the fresh wheel | `core_closure.scores: ran`, `fluxstd.core_log10_poly: ran` (review: `RuntimeError` for both) |
| `tools/wheel/test.py` against a fresh `tools/wheel/build.py` wheel | build `outputs/w4-3-20261031-02-wheel` (`rang_core-0.1.0-cp310-abi3-manylinux_2_35_x86_64.whl`, 3,204,938 B, sha256 `1e3bb393…78582`); test `outputs/w4-3-20261031-04-wheel-test` on 3.14 | **overall: PASS**. `kernels` step 0.56 s (closure median 0.0340, flux 23.25 Jy at 0.5 GHz). pytest 56 passed, 0 skipped |
| Targeted tests | `test_w4_3_kernels`, `test_core_closure`, `test_fluxstd`, `test_df2b_wgrid`, `test_pc1_preconditions`, `test_p5_memory` | 53 passed (35.3 s) |
| Clean pytest leaves no `core/target/*-standalone` | `c1-standalone` and `fs1-standalone` (built by the unchanged tree's baseline) deleted, then `bash tools/check-all.sh` | **none**: `core/target` holds only `debug` and `release` after the run |
| `bash tools/check-all.sh` | `outputs/w4-3-20261031-check-all.log`, branch at `0cebcbe` (the code; this report was committed after it) | **overall: PASS**; pytest 735 passed, 19 skipped in 301.5 s |

Rust lint on the extension crate: `cargo clippy --all-targets -D warnings`
and `cargo fmt --check` on `core/py` are clean.

## Deviations

- **The C1 checker.** The task names a "`rang-core` C1 checker", but
  `rang-core -h` has no C1 stage. The checker is `examples/check_c1.py`
  (`core_campaign_closure.check`), as in `research/c1-closure-arm.md` and
  PC1. It reads the archived run and never calls the kernel. The kernel's
  own bit-identity is therefore shown by the parity run, which compares the
  replaced standalone binary with the extension.
- **r05's probe.** The review's archived `r05_wheel_probe.py` stops at
  `core_receipts.source_receipts()`, which raises FileNotFoundError from a
  wheel (an unrelated finding; the review's own log shows the call wrapped).
  The copy in `outputs/w4-3-20261031-03-r05/` wraps that call in
  try/except, and its scratch path is `~/Build/tmp/20261031-w4-3/fakeproj`.
  Nothing else differs, and the kernel calls are verbatim. The first,
  unwrapped rerun stopped there (logged in the timings).
- **API kept as shims.** `core_closure.library()`, `library_path()`,
  `fluxstd.rust_library()` and `rust_log10_poly(lib, …)` stay, returning
  or using the extension. Their callers `core_campaign_closure.py` and
  `examples/check_fluxstd.py` are not owner files and need no edit.
  Removed: `core_closure.ClosureInputs`, `SOURCES` and `SYMBOLS`;
  `core_wgridder.library()`, `Options`, `SOURCES`, `SYMBOLS`,
  `EXTENSION_FUNCTIONS` and `_ptr`. No caller outside the modules used any
  of them (grep).
- **Flux standards are not bit-equal to the Python evaluator** on general
  grids. Rust's `powf` and NumPy's power differ in the last bit; FS1
  documented 1e-13. The new tests compare the two to within 1e-13. The
  Rust kernel itself is byte-identical before and after.
- **A stray build.** A first `maturin develop -m core/py/Cargo.toml`
  installed a wrong `rang-core-py` package into the worktree venv. It was
  uninstalled at once and the extension rebuilt with plain
  `maturin develop --release`. This was a venv-only error, and nothing on
  the branch is affected.
- **`docs/concepts/imaging.md`** still says the wgridder "is not yet bound
  in the extension". It is not an owner file, so the hunk is below.

## Tool runs

| Order (2026-10-31) | Tool | Input | Wall | Result |
| --- | --- | --- | --- | --- |
| 1 | `uv venv` and `uv pip install -e .[pointing,beam,test,imaging]` (with the extension build) | worktree | 237 s | ok |
| 2 | pytest `test_core_closure`, `test_fluxstd`, `test_df2b_wgrid` on the unchanged tree | builds `c1-` and `fs1-standalone` | 10.7 s | 31 passed |
| 3 | `parity.py dump` before | standalone builds | 1.8 s | 171 arrays, `65af587a…` |
| 4 | `check_fluxstd.py` before (first try without cargo on `PATH`: FileNotFoundError, 0.5 s) | FS1 runs 01, 03, 04, 06, O-CASA 01 | 0.37 s | equal to the archive except wall time |
| 5 | `check_c1.py` before (first try with the wrong precondition directory: FileNotFoundError, 0.4 s) | `c1-20261030-01`, `pc1-20261030-10-l1-fix` | 6.4 s | equal to `pc1-…-12` except `check_seconds` |
| 6 | `maturin develop --release -m core/py/Cargo.toml` (wrong invocation, see "Deviations") | `core/py` | 67.5 s | wrong package; uninstalled |
| 7 | `maturin develop --release` | `core/py` | 0.9 s | extension with both bindings |
| 8 | `parity.py dump` after and `compare`, no cargo | extension | < 2 s | byte-identical |
| 9 | `check_fluxstd.py` and `check_c1.py` after, no cargo | as before | 0.23 s / 5.4 s | as before |
| 10 | quick checks: ruff, `clippy -D warnings`, `cargo fmt --check` (`core/py`), targeted pytest | worktree | 36.3 s (pytest 35.3 s) | 53 passed; clean |
| 11 | `tools/wheel/build.py outputs/w4-3-20261031-02-wheel` | branch `0cebcbe` | 190.3 s | wheel built |
| 12 | `tools/wheel/test.py … outputs/w4-3-20261031-04-wheel-test --python 3.14` | that wheel | 28.3 s | overall PASS (56 passed) |
| 13 | r05, first rerun with the review's probe unchanged | that wheel | 0.9 s | stopped at `source_receipts` (unrelated) |
| 14 | r05 with the wrapped receipts call | that wheel | 0.95 s | both kernels ran |
| 15 | `bash tools/check-all.sh` (plain) | branch at `0cebcbe` | 672.6 s (lock wait included; pytest 301.5 s) | overall PASS, 735 passed, 19 skipped |

## For the coordinator

### Coordinator-file hunks

`core/src/lib.rs`: no change.

`core/py/src/lib.rs` (verbatim, against `ecccbf0`):

```diff
diff --git a/core/py/src/lib.rs b/core/py/src/lib.rs
index 3772cea..6cd0ea1 100644
--- a/core/py/src/lib.rs
+++ b/core/py/src/lib.rs
@@ -2054,6 +2054,176 @@ fn ms_read_cells<'py>(
     Ok(cells.into_iter().map(|c| cell_tuple(py, c)).collect())
 }
 
+// Task W4-3 (research/w4-3-kernels.md): the closure scores (C1) and the
+// flux-standard evaluator (FS1), which built a standalone library with Cargo
+// before. Each binding takes typed arrays (a wrong dtype is a TypeError),
+// refuses one that is not C-contiguous or not of the expected shape
+// (ValueError), calls the C function with the GIL released inside
+// `catch_unwind`, and raises on its status.
+
+/// Pointer of a C-contiguous input of exactly `shape`.
+fn exact_input<T: Element>(a: &Ro<'_, T>, name: &str, shape: &[usize]) -> PyResult<*const T> {
+    let view = a.as_array();
+    if !view.is_standard_layout() {
+        return Err(PyValueError::new_err(format!(
+            "{name} must be C-contiguous"
+        )));
+    }
+    if view.shape() != shape {
+        return Err(PyValueError::new_err(format!(
+            "{name} must have shape {shape:?}, not {:?}",
+            view.shape()
+        )));
+    }
+    ptr(a)
+}
+
+/// Pointer of a C-contiguous output of exactly `shape`.
+fn exact_output<T: Element>(a: &mut Rw<'_, T>, name: &str, shape: &[usize]) -> PyResult<*mut T> {
+    let view = a.as_array();
+    if !view.is_standard_layout() {
+        return Err(PyValueError::new_err(format!(
+            "{name} must be C-contiguous"
+        )));
+    }
+    if view.shape() != shape {
+        return Err(PyValueError::new_err(format!(
+            "{name} must have shape {shape:?}, not {:?}",
+            view.shape()
+        )));
+    }
+    ptr_mut(a)
+}
+
+/// The closure kernel's last error message on this thread.
+fn closure_last_error() -> String {
+    // SAFETY: a null buffer asks for the length only; `buf` then holds it.
+    let n =
+        unsafe { rang_core::ffi_closure::rang_core_closure_last_error(std::ptr::null_mut(), 0) };
+    let mut buf = vec![0_u8; n];
+    // SAFETY: `buf` holds `n` bytes.
+    unsafe { rang_core::ffi_closure::rang_core_closure_last_error(buf.as_mut_ptr(), n) };
+    String::from_utf8_lossy(&buf).into_owned()
+}
+
+/// `rang_core_closure_scores`: per-sample closure scores of one family.
+/// `data`, `model` (complex64) and `weights` (float32) are `(nrow, nchan,
+/// 4)`, `usable` (uint8) and the outputs `residual`, `tv` (float32) and
+/// `count` (uint16) `(nrow, nchan)`, the row columns (uint32) `(nrow,)`.
+/// Raises ValueError on invalid input (the core's message) and
+/// RuntimeError on a panic in the core.
+#[pyfunction]
+#[pyo3(signature = (
+    data, model, weights, usable, antenna1, antenna2, time_index, stations,
+    nant, ntime, family, min_closures, reroute, residual, tv, count
+))]
+#[allow(clippy::too_many_arguments)]
+fn closure_scores(
+    py: Python<'_>,
+    data: Ro<'_, Complex32>,
+    model: Ro<'_, Complex32>,
+    weights: Ro<'_, f32>,
+    usable: Ro<'_, u8>,
+    antenna1: Ro<'_, u32>,
+    antenna2: Ro<'_, u32>,
+    time_index: Ro<'_, u32>,
+    stations: Ro<'_, u32>,
+    nant: usize,
+    ntime: usize,
+    family: u32,
+    min_closures: u32,
+    reroute: u32,
+    mut residual: Rw<'_, f32>,
+    mut tv: Rw<'_, f32>,
+    mut count: Rw<'_, u16>,
+) -> PyResult<()> {
+    let shape = data.as_array().shape().to_vec();
+    if shape.len() != 3 || shape[2] != 4 {
+        return Err(PyValueError::new_err(format!(
+            "data must be (row, chan, 4), not {shape:?}"
+        )));
+    }
+    let (nrow, nchan) = (shape[0], shape[1]);
+    let nstation = stations.as_array().len();
+    let inputs = rang_core::ffi_closure::ClosureInputsC {
+        nrow,
+        nchan,
+        nant,
+        ntime,
+        nstation,
+        data: exact_input(&data, "data", &[nrow, nchan, 4])? as *const f32,
+        model: exact_input(&model, "model", &[nrow, nchan, 4])? as *const f32,
+        weights: exact_input(&weights, "weights", &[nrow, nchan, 4])?,
+        usable: exact_input(&usable, "usable", &[nrow, nchan])?,
+        antenna1: exact_input(&antenna1, "antenna1", &[nrow])?,
+        antenna2: exact_input(&antenna2, "antenna2", &[nrow])?,
+        time_index: exact_input(&time_index, "time_index", &[nrow])?,
+        stations: exact_input(&stations, "stations", &[nstation])?,
+        family,
+        min_closures,
+        reroute,
+    };
+    let residual = exact_output(&mut residual, "residual", &[nrow, nchan])?;
+    let tv = exact_output(&mut tv, "tv", &[nrow, nchan])?;
+    let count = exact_output(&mut count, "count", &[nrow, nchan])?;
+    // SAFETY: every pointer borrows a live NumPy buffer of the checked shape
+    // for the duration of the call; the outputs are distinct writable arrays.
+    let status = detach(py, || {
+        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
+            rang_core::ffi_closure::rang_core_closure_scores(&inputs, residual, tv, count)
+        }))
+        .unwrap_or(2)
+    });
+    match status {
+        0 => Ok(()),
+        1 => Err(PyValueError::new_err(format!(
+            "closure kernel failed (1): {}",
+            closure_last_error()
+        ))),
+        s => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
+            "closure kernel failed ({s}): a panic in the core"
+        ))),
+    }
+}
+
+/// `rang_core_fluxstd_eval`: `out[k] = 10^(sum_j coeffs[j] *
+/// log10(freq[k] / unit_hz)^j)`, all float64, `out` as long as `freq`.
+/// Raises ValueError when the core rejects the input (no coefficients, a
+/// non-positive frequency or unit) and RuntimeError on a panic.
+#[pyfunction]
+fn fluxstd_eval(
+    py: Python<'_>,
+    coeffs: Ro<'_, f64>,
+    unit_hz: f64,
+    freq: Ro<'_, f64>,
+    mut out: Rw<'_, f64>,
+) -> PyResult<()> {
+    let ncoeff = coeffs.as_array().len();
+    let nfreq = freq.as_array().len();
+    let coeffs = exact_input(&coeffs, "coeffs", &[ncoeff])?;
+    let freq = exact_input(&freq, "freq", &[nfreq])?;
+    let out = exact_output(&mut out, "out", &[nfreq])?;
+    // SAFETY: the pointers borrow live NumPy buffers of the checked lengths;
+    // `out` is a distinct writable array.
+    let status = detach(py, || {
+        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
+            rang_core::ffi_fluxstd::rang_core_fluxstd_eval(
+                ncoeff, coeffs, unit_hz, nfreq, freq, out,
+            )
+        }))
+        .unwrap_or(2)
+    });
+    match status {
+        0 => Ok(()),
+        1 => Err(PyValueError::new_err(
+            "rang_core_fluxstd_eval rejected its input (no coefficients, or a non-positive frequency or unit)",
+        )),
+        s => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
+            "rang_core_fluxstd_eval failed ({s}): a panic in the core"
+        ))),
+    }
+}
+
 /// The extension module `rang._core`.
 #[pymodule]
 fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
@@ -2111,5 +2281,7 @@ fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
     m.add_function(wrap_pyfunction!(ms_caltable_subtable, m)?)?;
     m.add_function(wrap_pyfunction!(ms_read_cells, m)?)?;
     m.add_function(wrap_pyfunction!(ms_array_records, m)?)?;
+    m.add_function(wrap_pyfunction!(closure_scores, m)?)?;
+    m.add_function(wrap_pyfunction!(fluxstd_eval, m)?)?;
     Ok(())
 }
```

### Non-owner stale text (optional)

`docs/concepts/imaging.md` (stale since DF2b):

```diff
-whole-array inputs ({gh}`research/df2-wgridder-speed.md`). It is not yet
-bound in the extension: on first use it builds a standalone library with
-`cargo` from a source checkout.
+whole-array inputs ({gh}`research/df2-wgridder-speed.md`). It runs in the
+extension `rang._core` (since DF2b; the standalone build is gone since
+W4-3, {gh}`research/w4-3-kernels.md`).
```

### `README.md` wording

```diff
-carries every kernel, the root crate's included (gain TV, phase trend,
-anchored response, projector, the pointing toy): the flagging chain and the
-notebooks run with no compiler. The Tricolour static masks and the archive
-drivers still read files from the checkout.
+carries every kernel, the root crate's included (gain TV, phase trend,
+anchored response, projector, the pointing toy), the exact wgridder, the
+closure statistic and the flux standards (since W4-3): the flagging chain
+and the notebooks run with no compiler. The Tricolour static masks and the
+archive drivers still read files from the checkout.
```

The sentence "nothing runs Cargo at import or at a kernel call" (README:136)
is now true and needs no change.

### STATE paragraph

> W4-3 (2026-10-31, implemented and measured; [w4-3-kernels.md](w4-3-kernels.md)):
> the closure scores and the flux-standard evaluator are bound in the
> extension (`closure_scores`, `fluxstd_eval`: sized, C-order checked, the GIL
> released, `catch_unwind`). No kernel call runs Cargo any more. The C1, FS1
> and DF1 standalone builders, the ctypes fallbacks and the dead P5 branch are
> deleted (−543 / +61 lines in four modules). The kernels are byte-identical to
> the standalone builds on 171 arrays. The C1 checker and the FS1 `setjy` check
> equal their archives except wall time. A wheel without cargo runs both
> kernels (r05; `tools/wheel/test.py` PASS with a new `kernels` step). This
> closes W4R-06 and W4R-16, and v0.1.0's "kernels in the wheel" item now passes.

### `research/README.md` index entry

> - [W4-3: closure and flux-standard kernels in the extension](w4-3-kernels.md): no kernel call runs Cargo; standalone builders and dead fallbacks deleted; byte-identical, wheel runs both (W4R-06, W4R-16).

### One-line notes for the two reports

- `research/c1-closure-arm.md`, at the "standalone crate" passages (lines
  373 and 642): "Since W4-3 the kernel runs in the extension
  (`rang._core.closure_scores`); the standalone build and `RANG_C1_LIB` are
  gone ([w4-3-kernels.md](w4-3-kernels.md))."
- `research/fs1-flux-standards.md`, at line 398: "Since W4-3 the kernel runs
  in the extension (`rang._core.fluxstd_eval`); the `fs1-standalone` build is
  gone ([w4-3-kernels.md](w4-3-kernels.md))."

### `research/tool-timings.md` rows

```
| 2026-10-31 | big plan W4-3: venv (`uv venv`, `uv pip install -e`) | worktree | 237 s | – | |
| 2026-10-31 | big plan W4-3: kernel parity before/after (`parity.py`) | 171 arrays | 1.8 s / < 2 s | – | byte-identical |
| 2026-10-31 | big plan W4-3: `check_c1.py` / `check_fluxstd.py`, no cargo | C1 frozen run / FS1 runs | 5.4 s / 0.23 s | – | equal to archives except wall time |
| 2026-10-31 | big plan W4-3: `maturin develop --release` | `core/py` | 0.9 s (a wrong first invocation 67.5 s) | – | |
| 2026-10-31 | big plan W4-3: `tools/wheel/build.py` | branch `0cebcbe` | 190.3 s | – | 3.2 MB wheel |
| 2026-10-31 | big plan W4-3: `tools/wheel/test.py` (3.14) | that wheel | 28.3 s | – | PASS, 56 passed |
| 2026-10-31 | big plan W4-3: r05 rerun | that wheel | 0.95 s | – | both kernels ran |
| 2026-10-31 | big plan W4-3: `bash tools/check-all.sh` | `0cebcbe` | 672.6 s (lock wait included; pytest 301.5 s) | – | overall PASS, 735 passed, 19 skipped |
```

### Ignored output directories

- `outputs/w4-3-20261031-01`: the parity script, the before and after
  `.npz` (keep `parity.py`, `*.json` and the check logs; the `.npz` files
  may be deleted), and the FS1 and C1 check outputs before and after.
- `outputs/w4-3-20261031-02-wheel` and `-02-wheel.log`: the wheel. It may be
  deleted after the merge (sha256 recorded above).
- `outputs/w4-3-20261031-03-r05`: the r05 driver, probe and log (keep).
- `outputs/w4-3-20261031-04-wheel-test` and `-04-wheel-test.log`: the
  wheel test with its venv. The venv may be deleted; keep the logs and
  `timings.tsv`.
- `outputs/w4-3-20261031-check-all.log`.
